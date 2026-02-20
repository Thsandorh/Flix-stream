import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import requests

from flix_stream.cache import ttl_cache
from flix_stream.config import (
    ANIWAYS_API_BASE,
    ANIWAYS_COMMON_HEADERS,
    COMMON_HEADERS,
    KITSU_API_BASE,
    PROVIDER_CACHE_MAXSIZE,
    PROVIDER_CACHE_TTL,
)


def decode_b64_loose(token):
    raw = str(token or "").strip()
    if not raw:
        return None
    padded = raw + ("=" * (-len(raw) % 4))
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(padded)
        except Exception:
            continue
    return None


def extract_aniways_proxy_hls_details(proxy_hls):
    """
    Aniways proxyHls format:
    /proxy/<provider>/<base64_json_headers>/<base64_target_url>
    """
    raw = str(proxy_hls or "").strip()
    if not raw:
        return None, {}

    marker = "/proxy/"
    idx = raw.find(marker)
    if idx < 0:
        return None, {}

    suffix = raw[idx + len(marker) :]
    parts = suffix.split("/", 2)
    if len(parts) < 3:
        return None, {}

    headers_token = parts[1].strip().split("?", 1)[0]
    target_token = parts[2].strip().split("?", 1)[0]

    parsed_headers = {}
    decoded_headers = decode_b64_loose(headers_token)
    if decoded_headers:
        try:
            header_payload = json.loads(decoded_headers.decode("utf-8"))
            if isinstance(header_payload, dict):
                name_map = {
                    "referer": "Referer",
                    "origin": "Origin",
                    "user-agent": "User-Agent",
                }
                for key, value in header_payload.items():
                    h_key = str(key or "").strip()
                    h_val = str(value or "").strip()
                    if not h_key or not h_val:
                        continue
                    parsed_headers[name_map.get(h_key.lower(), h_key)] = h_val
        except Exception:
            pass

    parsed_url = None
    decoded_url = decode_b64_loose(target_token)
    if decoded_url:
        try:
            candidate = decoded_url.decode("utf-8").strip()
            if candidate.startswith(("http://", "https://")):
                parsed_url = candidate
        except Exception:
            pass

    return parsed_url, parsed_headers


def is_likely_aniways_stream_url(url):
    """Filter obviously invalid Aniways candidates without probing upstream."""
    lowered = str(url or "").strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    if any(token in lowered for token in ("javascript:", "data:", "about:blank")):
        return False
    # Keep the working HLS patterns seen in Aniways responses.
    if ".m3u8" in lowered or "/hls-playback/" in lowered or "/proxy/" in lowered:
        return True
    return False


def is_aniways_api_proxy_url(url):
    lowered = str(url or "").strip().lower()
    return lowered.startswith("https://api.aniways.xyz/proxy/") or lowered.startswith(
        "http://api.aniways.xyz/proxy/"
    )


@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_aniways_streams(anime_id, episode_num):
    """Fetch stream links from Aniways for a specific anime and episode number."""
    try:
        episodes_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes"
        response_episode = requests.get(episodes_url, headers=ANIWAYS_COMMON_HEADERS, timeout=10)
        if response_episode.status_code != 200:
            return []

        episodes = response_episode.json()
        target_ep = None
        for episode in episodes:
            if str(episode.get("number")) == str(episode_num):
                target_ep = episode
                break

        if not target_ep:
            return []

        episode_id = target_ep.get("id")
        if not episode_id:
            return []

        servers_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes/{episode_id}/servers"
        response_server = requests.get(servers_url, headers=ANIWAYS_COMMON_HEADERS, timeout=10)
        if response_server.status_code != 200:
            return []

        servers = response_server.json()

        def _fetch_server_streams(srv):
            streams = []
            server_id = srv.get("serverId")
            server_name = srv.get("serverName")
            server_type = srv.get("type")
            if not server_id:
                return streams

            stream_api_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes/servers/{server_id}"

            try:
                server_candidates = []
                raw_server_name = str(server_name or "").strip()
                if raw_server_name:
                    server_candidates.append(raw_server_name)
                    server_candidates.append(raw_server_name.lower().replace(" ", "-"))
                    server_candidates.append(raw_server_name.lower())
                server_candidates = [
                    value
                    for idx, value in enumerate(server_candidates)
                    if value and value not in server_candidates[:idx]
                ]

                type_candidates = []
                raw_server_type = str(server_type or "").strip()
                if raw_server_type:
                    type_candidates.append(raw_server_type)
                    type_candidates.append(raw_server_type.lower())
                else:
                    type_candidates.append("")
                type_candidates = [
                    value for idx, value in enumerate(type_candidates) if value not in type_candidates[:idx]
                ]

                response_stream = None
                for server_param in server_candidates or [""]:
                    for type_param in type_candidates:
                        params = {"server": server_param, "type": type_param}
                        response_candidate = requests.get(
                            stream_api_url,
                            headers=ANIWAYS_COMMON_HEADERS,
                            params=params,
                            timeout=5,
                        )
                        if response_candidate.status_code == 200:
                            response_stream = response_candidate
                            break
                    if response_stream is not None:
                        break

                if response_stream is None:
                    return streams

                stream_data = response_stream.json()
                source_obj = stream_data.get("source") if isinstance(stream_data.get("source"), dict) else {}
                candidate_urls = []
                proxy_hls_headers = {}

                direct_url = stream_data.get("url")
                if isinstance(direct_url, str) and direct_url:
                    candidate_urls.append(direct_url)

                if isinstance(source_obj, dict):
                    source_hls = source_obj.get("hls") or source_obj.get("url")
                    if isinstance(source_hls, str) and source_hls:
                        candidate_urls.append(source_hls)

                    proxy_hls = source_obj.get("proxyHls")
                    if isinstance(proxy_hls, str) and proxy_hls:
                        resolved_proxy_url, resolved_proxy_headers = extract_aniways_proxy_hls_details(proxy_hls)
                        if resolved_proxy_url:
                            candidate_urls.append(resolved_proxy_url)
                            if resolved_proxy_headers:
                                proxy_hls_headers.update(resolved_proxy_headers)
                        else:
                            # Fallback only if we cannot decode proxyHls.
                            if proxy_hls.startswith("/"):
                                candidate_urls.append(f"https://aniways.xyz{proxy_hls}")
                            else:
                                candidate_urls.append(proxy_hls)

                # Keep order but remove duplicates.
                unique_urls = []
                seen_urls = set()
                for candidate in candidate_urls:
                    token = str(candidate or "").strip()
                    if not token or token in seen_urls:
                        continue
                    seen_urls.add(token)
                    unique_urls.append(token)
                if not unique_urls:
                    return streams

                # Prefer direct upstream media URLs over Aniways API proxy URLs when both exist.
                preferred_urls = [url for url in unique_urls if not is_aniways_api_proxy_url(url)]
                if preferred_urls:
                    unique_urls = preferred_urls

                # Keep one URL per server entry to avoid cluttered duplicate rows in clients.
                unique_urls = unique_urls[:1]

                request_headers = dict(ANIWAYS_COMMON_HEADERS)
                extra_headers = stream_data.get("headers")
                if isinstance(extra_headers, dict):
                    for h_key, h_val in extra_headers.items():
                        key = str(h_key or "").strip()
                        value = str(h_val or "").strip()
                        if not key or not value:
                            continue
                        request_headers[key] = value
                if proxy_hls_headers:
                    request_headers.update(proxy_hls_headers)

                subtitles = []
                for track in stream_data.get("tracks") or []:
                    if not isinstance(track, dict):
                        continue
                    sub_url = track.get("url") or track.get("raw")
                    if not isinstance(sub_url, str) or not sub_url:
                        continue
                    if sub_url.startswith("/"):
                        sub_url = f"https://aniways.xyz{sub_url}"
                    subtitles.append(
                        {
                            "id": str(track.get("label") or track.get("kind") or "Aniways"),
                            "lang": str(track.get("label") or "und"),
                            "url": sub_url,
                        }
                    )

                for stream_url in unique_urls:
                    variant = str(server_type or "").upper() or "SUB"
                    stream_title = f"[Aniways] Episode {episode_num} - {server_name or 'Server'} [{variant}]"

                    if not is_likely_aniways_stream_url(stream_url):
                        continue

                    stream_obj = {
                        "name": f"Aniways - {server_name or 'Server'} [{variant}]",
                        "title": stream_title,
                        "url": stream_url,
                        "behaviorHints": {
                            "notWebReady": True,
                            "proxyHeaders": {"request": request_headers},
                        },
                    }
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                    streams.append(stream_obj)
            except Exception:
                return []
            return streams

        streams = []
        with ThreadPoolExecutor(max_workers=min(8, len(servers) or 1)) as executor:
            for server_streams in executor.map(_fetch_server_streams, servers):
                streams.extend(server_streams)
        return streams
    except Exception:
        return []


def normalize_title_for_match(value):
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


@lru_cache(maxsize=1024)
def get_kitsu_anime_context(kitsu_id):
    """Fetch Kitsu anime metadata and cross-site mappings for Aniways resolution."""
    titles = []
    mal_id = None
    anilist_id = None

    headers = {"User-Agent": COMMON_HEADERS["User-Agent"]}
    anime_url = f"{KITSU_API_BASE}/anime/{kitsu_id}"
    mappings_url = f"{KITSU_API_BASE}/anime/{kitsu_id}/mappings"

    def _fetch_json(url):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return None
            return response.json()
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        anime_payload, mappings_payload = executor.map(_fetch_json, [anime_url, mappings_url])

    try:
        data = anime_payload.get("data") if isinstance(anime_payload, dict) else None
        attrs = data.get("attributes") if isinstance(data, dict) else None
        if isinstance(attrs, dict):
            canonical = attrs.get("canonicalTitle")
            if canonical:
                titles.append(canonical)
            title_map = attrs.get("titles")
            if isinstance(title_map, dict):
                for val in title_map.values():
                    if val:
                        titles.append(val)
            abbreviated = attrs.get("abbreviatedTitles")
            if isinstance(abbreviated, list):
                for val in abbreviated:
                    if val:
                        titles.append(val)
    except Exception:
        pass

    try:
        data = mappings_payload.get("data") if isinstance(mappings_payload, dict) else []
        if isinstance(data, list):
            for mapping in data:
                attrs = mapping.get("attributes") if isinstance(mapping, dict) else None
                if not isinstance(attrs, dict):
                    continue
                site = str(attrs.get("externalSite") or "").lower()
                ext_raw = attrs.get("externalId")
                try:
                    ext_id = int(ext_raw)
                except Exception:
                    continue

                if site == "myanimelist/anime" and mal_id is None:
                    mal_id = ext_id
                elif site == "anilist/anime" and anilist_id is None:
                    anilist_id = ext_id
    except Exception:
        pass

    unique_titles = []
    seen = set()
    for title in titles:
        token = str(title).strip()
        if len(token) < 3:
            continue
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        unique_titles.append(token)

    return {"titles": unique_titles, "mal_id": mal_id, "anilist_id": anilist_id}


@lru_cache(maxsize=2048)
def fetch_aniways_search_page(query, page=1, items_per_page=20):
    params = {"q": query, "page": page, "itemsPerPage": items_per_page}
    try:
        response = requests.get(
            f"{ANIWAYS_API_BASE}/anime/listings/search",
            headers=ANIWAYS_COMMON_HEADERS,
            params=params,
            timeout=10,
        )
        if response.status_code != 200:
            return []
        payload = response.json()
        items = payload.get("items") if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []
    except Exception:
        return []


@lru_cache(maxsize=1024)
def get_aniways_anime_context(anime_id):
    """Fetch Aniways metadata for subtitle/ID enrichment flows."""
    titles = []
    media_type = None
    season_year = None

    try:
        response = requests.get(
            f"{ANIWAYS_API_BASE}/anime/{anime_id}",
            headers=ANIWAYS_COMMON_HEADERS,
            timeout=10,
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("ename", "jname"):
                    value = str(payload.get(key) or "").strip()
                    if value:
                        titles.append(value)

                metadata = payload.get("metadata")
                if isinstance(metadata, dict):
                    media_type = str(metadata.get("mediaType") or "").strip().lower() or None
                    year_raw = metadata.get("seasonYear")
                    try:
                        season_year = int(year_raw) if year_raw is not None else None
                    except Exception:
                        season_year = None
    except Exception:
        pass

    unique_titles = []
    seen = set()
    for title in titles:
        lowered = title.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_titles.append(title)

    return {
        "titles": unique_titles,
        "media_type": media_type,
        "season_year": season_year,
    }


@lru_cache(maxsize=1024)
def resolve_aniways_id_from_kitsu(kitsu_id):
    """Resolve Aniways anime id from a Kitsu anime id using mappings + title search."""
    ctx = get_kitsu_anime_context(kitsu_id)
    titles = ctx.get("titles") or []
    mal_id = ctx.get("mal_id")
    anilist_id = ctx.get("anilist_id")
    if not titles:
        return None

    primary_titles = titles[:6]
    secondary_titles = titles[:4]
    ordered_queries = []
    seen_queries = set()
    for title in primary_titles + secondary_titles:
        token = str(title or "").strip()
        if not token or token in seen_queries:
            continue
        seen_queries.add(token)
        ordered_queries.append(token)

    search_results = {}
    with ThreadPoolExecutor(max_workers=min(6, len(ordered_queries) or 1)) as executor:
        for title, items in zip(
            ordered_queries,
            executor.map(lambda q: fetch_aniways_search_page(q, page=1, items_per_page=20), ordered_queries),
        ):
            search_results[title] = items

    # First pass: exact external-id match (most reliable).
    for title in primary_titles:
        items = search_results.get(str(title).strip(), [])
        for item in items:
            item_mal = item.get("malId")
            item_anilist = item.get("anilistId")
            if mal_id is not None and item_mal == mal_id:
                return item.get("id")
            if anilist_id is not None and item_anilist == anilist_id:
                return item.get("id")

    # Second pass: title similarity fallback.
    normalized_titles = {normalize_title_for_match(title) for title in titles if title}
    for title in secondary_titles:
        items = search_results.get(str(title).strip(), [])
        for item in items:
            names = [item.get("ename"), item.get("jname")]
            for name in names:
                if normalize_title_for_match(name) in normalized_titles:
                    return item.get("id")

    return None
