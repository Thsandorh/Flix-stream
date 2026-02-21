import logging
import re
from urllib.parse import urlencode

import requests

from flix_stream.config import (
    AUTOEMBED_COMMON_HEADERS,
    COMMON_HEADERS,
    PROVIDER_CACHE_MAXSIZE,
    PROVIDER_CACHE_TTL,
    VIXSRC_BASE_URL,
    VIXSRC_COMMON_HEADERS,
)
from flix_stream.cache import ttl_cache
from flix_stream.crypto import decrypt_autoembed_response, decrypt_link
from flix_stream.subtitles import parse_subtitles
from flix_stream.hdhub4u import fetch_hdhub4u_streams
from flix_stream.tmdb import get_imdb_id_from_tmdb, get_tmdb_title


logger = logging.getLogger(__name__)


def needs_stremio_proxy(decrypted_url):
    """Avoid double-proxying already wrapped upstream proxy URLs."""
    lowered = str(decrypted_url or "").lower()
    if "/proxy/m3u8/" in lowered or "/proxy/hls/" in lowered:
        return False
    return True


@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_server_streams(tmdb_id, sr_info, season, episode, decryption_key):
    """Worker function to fetch streams from a specific server."""
    sr = sr_info["id"]
    api_url = f"https://player.vidzee.wtf/api/server?id={tmdb_id}&sr={sr}"
    if season and episode:
        api_url += f"&ss={season}&ep={episode}"

    streams = []
    try:
        response = requests.get(api_url, headers=COMMON_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        # The key might be "subtitle", "subtitles", or "tracks" depending on API response.
        raw_subs = data.get("subtitle", [])
        if not raw_subs:
            raw_subs = data.get("subtitles", [])
        if not raw_subs:
            raw_subs = data.get("tracks", [])

        subtitles = parse_subtitles(raw_subs)

        if data.get("url"):
            for stream_candidate in data["url"]:
                decrypted_url = decrypt_link(stream_candidate["link"], decryption_key)
                if decrypted_url:
                    behavior_hints = {}
                    if needs_stremio_proxy(decrypted_url):
                        behavior_hints = {
                            "notWebReady": True,
                            "proxyHeaders": {"request": COMMON_HEADERS},
                        }

                    stream_obj = {
                        "name": f"VidZee - {sr_info['name']}",
                        "title": f"[VidZee] {stream_candidate.get('lang', 'English')} {stream_candidate.get('message', '')}\n{stream_candidate.get('name', '')}",
                        "url": decrypted_url,
                    }
                    if behavior_hints:
                        stream_obj["behaviorHints"] = behavior_hints
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                    streams.append(stream_obj)
    except Exception as exc:
        logger.error("Error fetching streams for server %s: %s", sr, exc)
    return streams


@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_autoembed_server_streams(tmdb_id, sr_info, season, episode):
    """Fetch streams from AutoEmbed API for one server."""
    sr = sr_info["id"]
    api_url = f"https://test.autoembed.cc/api/server?id={tmdb_id}&sr={sr}"
    if season and episode:
        api_url += f"&ss={season}&ep={episode}"
        referer = f"https://test.autoembed.cc/embed/tv/{tmdb_id}/{season}/{episode}"
    else:
        referer = f"https://test.autoembed.cc/embed/movie/{tmdb_id}"

    headers = AUTOEMBED_COMMON_HEADERS.copy()
    headers["Referer"] = referer

    streams = []
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        decrypted_data = decrypt_autoembed_response(data)
        if not decrypted_data:
            return streams

        raw_subs = (
            decrypted_data.get("tracks", [])
            or decrypted_data.get("subtitles", [])
            or decrypted_data.get("subtitle", [])
        )
        subtitles = parse_subtitles(raw_subs)

        stream_url = decrypted_data.get("url")
        url_candidates = stream_url if isinstance(stream_url, list) else [stream_url]
        for candidate in url_candidates:
            if not candidate:
                continue
            stream_obj = {
                "name": f"AutoEmbed - {sr_info['name']}",
                "title": f"[AutoEmbed] {sr_info['name']}",
                "url": candidate,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {"request": headers},
                },
            }
            if subtitles:
                stream_obj["subtitles"] = subtitles
            streams.append(stream_obj)
    except Exception as exc:
        logger.error("Error fetching AutoEmbed streams for server %s: %s", sr, exc)
    return streams


def extract_braced_js_object(text, from_index):
    start = str(text or "").find("{", max(0, int(from_index or 0)))
    if start < 0:
        return None

    depth = 0
    in_string = None
    escaped = False
    payload = str(text)

    for idx in range(start, len(payload)):
        char = payload[idx]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == in_string:
                in_string = None
            continue

        if char in ("'", '"'):
            in_string = char
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return payload[start : idx + 1]
    return None


def extract_vixsrc_playlist_url(html_text):
    html = str(html_text or "")
    marker = "window.masterPlaylist"
    marker_idx = html.find(marker)
    if marker_idx < 0:
        return None

    assign_idx = html.find("=", marker_idx)
    if assign_idx < 0:
        return None

    master_obj = extract_braced_js_object(html, assign_idx)
    if not master_obj:
        return None

    url_match = re.search(r"url\s*:\s*['\"]([^'\"]+)['\"]", master_obj)
    if not url_match:
        return None
    base_url = url_match.group(1).strip()
    if not base_url:
        return None
    if base_url.startswith("/"):
        base_url = f"{VIXSRC_BASE_URL}{base_url}"

    params = {}
    params_key = re.search(r"\bparams\s*:", master_obj)
    if params_key:
        params_obj = extract_braced_js_object(master_obj, params_key.end())
        if params_obj:
            pairs = re.findall(
                r"['\"]?([a-zA-Z0-9_]+)['\"]?\s*:\s*(?:['\"]([^'\"]*)['\"]|([0-9]+(?:\.[0-9]+)?|true|false|null))",
                params_obj,
            )
            for key, str_val, raw_val in pairs:
                if str_val != "":
                    params[key] = str(str_val).strip()
                elif raw_val != "":
                    params[key] = str(raw_val).strip()
                else:
                    params[key] = ""

    params["h"] = "1"
    if not params.get("lang"):
        params["lang"] = "en"

    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(params)}"


@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_vixsrc_streams(tmdb_id, content_type, season, episode):
    """Fetch stream links from VixSrc by decoding window.masterPlaylist from the embed page."""
    media_type = "tv" if str(content_type or "").lower() in ("series", "tv") else "movie"
    if media_type == "tv":
        if not season or not episode:
            return []
        embed_url = f"{VIXSRC_BASE_URL}/tv/{tmdb_id}/{season}/{episode}"
        title_suffix = f"S{season}E{episode}"
    else:
        embed_url = f"{VIXSRC_BASE_URL}/movie/{tmdb_id}"
        title_suffix = "Movie"

    request_headers = {
        "User-Agent": VIXSRC_COMMON_HEADERS["User-Agent"],
        "Referer": VIXSRC_COMMON_HEADERS["Referer"],
    }

    try:
        response = requests.get(embed_url, headers=request_headers, timeout=10)
        response.raise_for_status()
        playlist_url = extract_vixsrc_playlist_url(response.text)
        if not playlist_url:
            return []

        return [
            {
                "name": "VixSrc",
                "title": f"[VixSrc] {title_suffix}",
                "url": playlist_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {"request": dict(VIXSRC_COMMON_HEADERS)},
                },
            }
        ]
    except Exception as exc:
        logger.error("Error fetching VixSrc streams for TMDB %s: %s", tmdb_id, exc)
        return []


@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_hdhub4u_streams_worker(tmdb_id, content_type, season, episode):
    """Fetch streams from HDHub4u using TMDB metadata."""
    try:
        # Get metadata
        imdb_id = get_imdb_id_from_tmdb(tmdb_id, content_type)
        title = get_tmdb_title(tmdb_id, content_type)

        if not title and not imdb_id:
            logger.warning("HDHub4u: Could not resolve title or IMDb ID for TMDB %s", tmdb_id)
            return []

        return fetch_hdhub4u_streams(tmdb_id, imdb_id, title, season, episode)
    except Exception as exc:
        logger.error("Error fetching HDHub4u streams for TMDB %s: %s", tmdb_id, exc)
        return []
