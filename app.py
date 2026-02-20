import json
import os
import re
import base64
import hashlib
import time
import requests
from urllib.parse import unquote
from functools import lru_cache
from flask import Flask, jsonify, render_template, request
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Util.Padding import unpad
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# Config
# For a production addon, these should be moved to environment variables.
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0YzY4ZTRjYjBhMDM4OTk0MTliNmVmYTZiOGJjOGJiZSIsIm5iZiI6MTcyNzUwNjM2NS40NDQxNjUsInN1YiI6IjY2NWQ5YmMwYTVlMDU0MzUwMTQ5MWUwNSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.8OL7WQIZGWr9tRfmSkRFIsaf1Wy0ksrOGDCB4KcocW4")
MASTER_KEY = "b3f2a9d4c6e1f8a7b"

MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.0.34",
    "name": "Flix-Streams",
    "description": "Stream movies and series from VidZee, AutoEmbed, Aniways, and Kitsu IDs.",
    "logo": "/static/icon.png",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt", "aniways", "kitsu"],
    "catalogs": []
}

SERVERS = [
    {"id": "1", "name": "Duke"},
    {"id": "2", "name": "Glory"},
    {"id": "4", "name": "Atlas"},
    {"id": "5", "name": "Drag"},
    {"id": "6", "name": "Achilles"},
    {"id": "9", "name": "Hindi"},
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://player.vidzee.wtf/",
    "Origin": "https://player.vidzee.wtf"
}

AUTOEMBED_SERVERS = [
    {"id": "2", "name": "Glory"},
    {"id": "3", "name": "Server 3"},
    {"id": "7", "name": "Server 7"},
    {"id": "9", "name": "Hindi"},
]

AUTOEMBED_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": "https://test.autoembed.cc/",
    "Origin": "https://test.autoembed.cc",
}

ANIWAYS_API_BASE = "https://api.aniways.xyz"
ANIWAYS_COMMON_HEADERS = {
    "User-Agent": COMMON_HEADERS["User-Agent"],
    "Referer": "https://aniways.xyz/",
    "Origin": "https://aniways.xyz",
}
KITSU_API_BASE = "https://kitsu.io/api/edge"

LANG_MAP = {
    "English": "eng",
    "French": "fre",
    "German": "ger",
    "Spanish": "spa",
    "Italian": "ita",
    "Portuguese": "por",
    "Portuguese (BR)": "pob",
    "Hungarian": "hun",
    "Russian": "rus",
    "Ukrainian": "ukr",
    "Dutch": "nld",
    "Polish": "pol",
    "Romanian": "rum",
    "Czech": "cze",
    "Greek": "gre",
    "Turkish": "tur",
    "Arabic": "ara",
    "Hebrew": "heb",
    "Japanese": "jpn",
    "Korean": "kor",
    "Chinese": "chi", "Chinese (traditional)": "chi",
    "Vietnamese": "vie",
    "Thai": "tha",
    "Indonesian": "ind",
    "Swedish": "swe",
    "Norwegian": "nor",
    "Danish": "dan",
    "Finnish": "fin",
    "Slovak": "slo",
    "Slovenian": "slv",
    "Croatian": "hrv",
    "Serbian": "srp",
    "Bulgarian": "bul",
    "Estonian": "est",
    "Latvian": "lav",
    "Lithuanian": "lit",
    "Malay": "may",
    "Persian": "per",
    "Albanian": "sqi",
    "Macedonian": "mkd",
    "Bosnian": "bos",
}

# Simple cache for decryption key
_KEY_CACHE = {"key": None, "timestamp": 0}

def get_decryption_key():
    """Fetches and decrypts the current VidZee API key with caching (1 hour)."""
    now = time.time()
    if _KEY_CACHE["key"] and (now - _KEY_CACHE["timestamp"] < 3600):
        return _KEY_CACHE["key"]

    try:
        r = requests.get("https://core.vidzee.wtf/api-key", headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        encrypted_data = base64.b64decode(r.text.strip())

        if len(encrypted_data) <= 28:
            return None

        iv = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        key = hashlib.sha256(MASTER_KEY.encode()).digest()
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted_key = cipher.decrypt_and_verify(ciphertext, tag).decode()
        
        # Update cache
        _KEY_CACHE["key"] = decrypted_key
        _KEY_CACHE["timestamp"] = now
        return decrypted_key
    except Exception as e:
        app.logger.error(f"Failed to get decryption key: {e}")
        return None

def decrypt_link(encrypted_link, key_str):
    """Decrypts a VidZee server link using AES-CBC."""
    try:
        decoded = base64.b64decode(encrypted_link).decode()
        if ':' not in decoded:
            return None

        iv_b64, cipher_b64 = decoded.split(':')
        iv = base64.b64decode(iv_b64)
        ciphertext = base64.b64decode(cipher_b64)

        key = key_str.encode().ljust(32, b'\0')
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decrypted = cipher.decrypt(ciphertext)

        padding_len = decrypted[-1]
        if padding_len > 16: # Sanity check for padding
            return None

        return decrypted[:-padding_len].decode()
    except Exception:
        return None

@lru_cache(maxsize=2048)
def get_tmdb_id(imdb_id, content_type=None):
    """Maps IMDb id to TMDB id with type-aware selection."""
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}", "User-Agent": COMMON_HEADERS["User-Agent"]}
    kind = (content_type or "").lower()

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        movie_results = data.get("movie_results") or []
        tv_results = data.get("tv_results") or []
        tv_episode_results = data.get("tv_episode_results") or []
        tv_season_results = data.get("tv_season_results") or []
        tv_season_show_id = next(
            (item.get("show_id") for item in tv_season_results if item.get("show_id")),
            None,
        )

        if kind in ("series", "tv"):
            if tv_results:
                return tv_results[0]["id"]
            if tv_episode_results and tv_episode_results[0].get("show_id"):
                return tv_episode_results[0]["show_id"]
            if tv_season_show_id:
                return tv_season_show_id
            return None

        if kind == "movie":
            if movie_results:
                return movie_results[0]["id"]
            return None

        # Fallback if type is unknown.
        if movie_results:
            return movie_results[0]["id"]
        if tv_results:
            return tv_results[0]["id"]
        if tv_episode_results and tv_episode_results[0].get("show_id"):
            return tv_episode_results[0]["show_id"]
        if tv_season_show_id:
            return tv_season_show_id
    except Exception as e:
        app.logger.error(f"TMDB mapping failed for {imdb_id}: {e}")

    # Fallback: Cinemeta often still exposes moviedb_id when TMDB /find misses.
    fallback_tmdb_id = get_tmdb_id_from_cinemeta(imdb_id, kind)
    if fallback_tmdb_id:
        return fallback_tmdb_id

    return None

@lru_cache(maxsize=2048)
def get_tmdb_id_from_cinemeta(imdb_id, content_type=None):
    """Fallback IMDb->TMDB mapping via Cinemeta meta endpoint."""
    kind = (content_type or "").lower()
    if kind in ("series", "tv"):
        meta_types = ["series"]
    elif kind == "movie":
        meta_types = ["movie"]
    else:
        meta_types = ["movie", "series"]

    headers = {"User-Agent": COMMON_HEADERS["User-Agent"]}
    for meta_type in meta_types:
        url = f"https://v3-cinemeta.strem.io/meta/{meta_type}/{imdb_id}.json"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            meta = data.get("meta") if isinstance(data, dict) else None
            moviedb_id = meta.get("moviedb_id") if isinstance(meta, dict) else None
            if moviedb_id is None:
                continue
            return int(moviedb_id)
        except Exception:
            continue

    return None

@lru_cache(maxsize=2048)
def get_series_context_from_imdb(imdb_id):
    """Resolve show/season/episode context from an IMDb episode id."""
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}", "User-Agent": COMMON_HEADERS["User-Agent"]}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        tv_episode_results = data.get("tv_episode_results") or []
        if tv_episode_results:
            item = tv_episode_results[0]
            return item.get("show_id"), item.get("season_number"), item.get("episode_number")

        tv_season_results = data.get("tv_season_results") or []
        if tv_season_results:
            item = tv_season_results[0]
            return item.get("show_id"), item.get("season_number"), None
    except Exception as e:
        app.logger.error(f"TMDB series context lookup failed for {imdb_id}: {e}")

    return None, None, None

def _decode_stream_id(raw_id):
    """Decode URL-encoded stream ids, including double-encoded variants."""
    decoded = str(raw_id or "")
    for _ in range(2):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded

def _normalize_episode_part(value):
    if value is None:
        return None
    token = str(value).strip()
    if not token:
        return None
    if token.isdigit():
        return str(int(token))
    m = re.search(r"\d+", token)
    if m:
        return str(int(m.group(0)))
    return None

def _needs_stremio_proxy(decrypted_url):
    """Avoid double-proxying already wrapped upstream proxy URLs."""
    lowered = str(decrypted_url or "").lower()
    if "/proxy/m3u8/" in lowered or "/proxy/hls/" in lowered:
        return False
    return True

def decrypt_autoembed_response(data_json):
    """Decrypt AutoEmbed API response using PBKDF2 and AES-CBC."""
    try:
        payload = data_json
        if isinstance(payload, dict) and "data" in payload:
            inner_json_str = base64.b64decode(payload["data"]).decode("utf-8")
            payload = json.loads(inner_json_str)

        key_hex = payload.get("key")
        iv_hex = payload.get("iv")
        salt_hex = payload.get("salt")
        iterations = int(payload.get("iterations", 0))
        encrypted_data_b64 = payload.get("encryptedData")

        if not all([key_hex, iv_hex, salt_hex, encrypted_data_b64]) or iterations <= 0:
            return None

        salt = bytes.fromhex(salt_hex)
        iv = bytes.fromhex(iv_hex)
        encrypted_data = base64.b64decode(encrypted_data_b64)
        key = PBKDF2(key_hex, salt, dkLen=32, count=iterations, hmac_hash_module=SHA256)

        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
        return json.loads(decrypted_data.decode("utf-8"))
    except Exception as e:
        app.logger.error(f"AutoEmbed response decryption failed: {e}")
        return None

def parse_subtitles(subtitle_list):
    """Parses VidZee subtitle list into Stremio format."""
    parsed = []
    if not subtitle_list:
        return parsed

    for sub in subtitle_list:
        lang_name = sub.get("lang", "")
        url = sub.get("url", "")
        if not url:
            continue
            
        # Try to map language name to ISO 639-2
        # Use simple mapping
        iso_code = LANG_MAP.get(lang_name)
        if not iso_code:
             # Try stripping numbers at end? "English2" -> "English"
             base_lang = re.sub(r'\d+$', '', lang_name).strip()
             iso_code = LANG_MAP.get(base_lang)

        if not iso_code:
             # Just use the name if we can't map it.
             # Ideally Stremio wants 3-letter codes but it might fallback gracefully.
             iso_code = lang_name

        parsed.append({
            "url": url,
            "lang": iso_code,
            "id": lang_name # Use original name as ID to be unique
        })
    return parsed

def fetch_server_streams(tmdb_id, sr_info, season, episode, decryption_key):
    """Worker function to fetch streams from a specific server."""
    sr = sr_info["id"]
    api_url = f"https://player.vidzee.wtf/api/server?id={tmdb_id}&sr={sr}"
    if season and episode:
        api_url += f"&ss={season}&ep={episode}"

    streams = []
    try:
        r = requests.get(api_url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Parse subtitles if available
        # The key might be "subtitle", "subtitles", or "tracks" depending on API version/response
        raw_subs = data.get("subtitle", [])
        if not raw_subs:
            raw_subs = data.get("subtitles", [])
        if not raw_subs:
            raw_subs = data.get("tracks", [])
            
        subtitles = parse_subtitles(raw_subs)
        
        if data.get("url"):
            for u in data["url"]:
                decrypted_url = decrypt_link(u["link"], decryption_key)
                if decrypted_url:
                    behavior_hints = {}
                    if _needs_stremio_proxy(decrypted_url):
                        behavior_hints = {
                            "notWebReady": True,
                            "proxyHeaders": {
                                "request": COMMON_HEADERS
                            }
                        }

                    stream_obj = {
                        "name": f"VidZee - {sr_info['name']}",
                        "title": f"[VidZee] {u.get('lang', 'English')} {u.get('message', '')}\n{u.get('name', '')}",
                        "url": decrypted_url
                    }
                    if behavior_hints:
                        stream_obj["behaviorHints"] = behavior_hints
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                    streams.append(stream_obj)
    except Exception as e:
        app.logger.error(f"Error fetching streams for server {sr}: {e}")
    return streams

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
        r = requests.get(api_url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
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
                    "proxyHeaders": {
                        "request": headers
                    }
                }
            }
            if subtitles:
                stream_obj["subtitles"] = subtitles
            streams.append(stream_obj)
    except Exception as e:
        app.logger.error(f"Error fetching AutoEmbed streams for server {sr}: {e}")
    return streams

def fetch_aniways_streams(anime_id, episode_num):
    """Fetch stream links from Aniways for a specific anime and episode number."""
    try:
        episodes_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes"
        r_ep = requests.get(episodes_url, headers=ANIWAYS_COMMON_HEADERS, timeout=10)
        if r_ep.status_code != 200:
            return []

        episodes = r_ep.json()
        target_ep = None
        for ep in episodes:
            if str(ep.get("number")) == str(episode_num):
                target_ep = ep
                break

        if not target_ep:
            return []

        episode_id = target_ep.get("id")
        if not episode_id:
            return []

        servers_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes/{episode_id}/servers"
        r_srv = requests.get(servers_url, headers=ANIWAYS_COMMON_HEADERS, timeout=10)
        if r_srv.status_code != 200:
            return []

        servers = r_srv.json()
        streams = []
        for srv in servers:
            server_id = srv.get("serverId")
            server_name = srv.get("serverName")
            server_type = srv.get("type")
            if not server_id:
                continue

            stream_api_url = f"{ANIWAYS_API_BASE}/anime/{anime_id}/episodes/servers/{server_id}"
            params = {
                "server": server_name.lower().replace(" ", "-") if server_name else "",
                "type": server_type.lower() if server_type else ""
            }

            try:
                r_stream = requests.get(
                    stream_api_url,
                    headers=ANIWAYS_COMMON_HEADERS,
                    params=params,
                    timeout=5
                )
                if r_stream.status_code != 200:
                    continue

                stream_data = r_stream.json()
                source_obj = stream_data.get("source") if isinstance(stream_data.get("source"), dict) else {}
                candidate_urls = []

                direct_url = stream_data.get("url")
                if isinstance(direct_url, str) and direct_url:
                    candidate_urls.append(direct_url)

                if isinstance(source_obj, dict):
                    source_hls = source_obj.get("hls") or source_obj.get("url")
                    if isinstance(source_hls, str) and source_hls:
                        candidate_urls.append(source_hls)

                    proxy_hls = source_obj.get("proxyHls")
                    if isinstance(proxy_hls, str) and proxy_hls:
                        if proxy_hls.startswith("/"):
                            candidate_urls.append(f"https://aniways.xyz{proxy_hls}")
                            candidate_urls.append(f"{ANIWAYS_API_BASE}{proxy_hls}")
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
                    continue

                request_headers = dict(ANIWAYS_COMMON_HEADERS)
                extra_headers = stream_data.get("headers")
                if isinstance(extra_headers, dict):
                    request_headers.update(extra_headers)

                # Try to extract headers from proxyHls if present
                proxy_hls_path = source_obj.get("proxyHls") if isinstance(source_obj, dict) else None
                if isinstance(proxy_hls_path, str) and proxy_hls_path.startswith("/proxy/"):
                    try:
                        # proxyHls format: /proxy/<provider>/<base64_headers>/<base64_url>
                        parts = proxy_hls_path.split('/')
                        if len(parts) >= 4:
                            b64_headers = parts[3]
                            # Add padding if needed
                            missing_padding = len(b64_headers) % 4
                            if missing_padding:
                                b64_headers += '=' * (4 - missing_padding)

                            decoded_headers = base64.b64decode(b64_headers).decode('utf-8')
                            proxy_headers_json = json.loads(decoded_headers)
                            if isinstance(proxy_headers_json, dict):
                                # Normalize headers to avoid duplicates with different casing
                                for k, v in proxy_headers_json.items():
                                    # Remove existing key with same name (case-insensitive)
                                    for existing_k in list(request_headers.keys()):
                                        if existing_k.lower() == k.lower():
                                            del request_headers[existing_k]
                                    request_headers[k] = v
                    except Exception as e:
                        # Log error but continue with default headers
                        app.logger.warning(f"Failed to extract headers from proxyHls: {e}")

                subtitles = []
                for track in (stream_data.get("tracks") or []):
                    if not isinstance(track, dict):
                        continue
                    sub_url = track.get("url") or track.get("raw")
                    if not isinstance(sub_url, str) or not sub_url:
                        continue
                    if sub_url.startswith("/"):
                        sub_url = f"https://aniways.xyz{sub_url}"
                    subtitles.append({
                        "id": str(track.get("label") or track.get("kind") or "Aniways"),
                        "lang": str(track.get("label") or "und"),
                        "url": sub_url,
                    })

                for idx, stream_url in enumerate(unique_urls, start=1):
                    stream_title = f"[Aniways] Episode {episode_num} - {server_name or 'Server'}"
                    if len(unique_urls) > 1:
                        stream_title = f"{stream_title} (Source {idx})"

                    if not _is_likely_aniways_stream_url(stream_url):
                        continue

                    stream_obj = {
                        "name": f"Aniways - {server_name or 'Server'}",
                        "title": stream_title,
                        "url": stream_url,
                        "behaviorHints": {
                            "notWebReady": True,
                            "proxyHeaders": {
                                "request": request_headers
                            }
                        }
                    }
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                    streams.append(stream_obj)
            except Exception:
                continue

        return streams
    except Exception:
        return []

def _is_likely_aniways_stream_url(url):
    """Filter obviously invalid Aniways candidates without probing upstream."""
    u = str(url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return False
    if any(x in u for x in ("javascript:", "data:", "about:blank")):
        return False
    # Keep the working HLS patterns seen in Aniways responses.
    if ".m3u8" in u or "/hls-playback/" in u:
        return True
    return False

def _normalize_title_for_match(value):
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())

@lru_cache(maxsize=1024)
def get_kitsu_anime_context(kitsu_id):
    """Fetch Kitsu anime metadata and cross-site mappings for Aniways resolution."""
    titles = []
    mal_id = None
    anilist_id = None

    try:
        anime_url = f"{KITSU_API_BASE}/anime/{kitsu_id}"
        r_anime = requests.get(anime_url, headers={"User-Agent": COMMON_HEADERS["User-Agent"]}, timeout=10)
        if r_anime.status_code == 200:
            payload = r_anime.json()
            data = payload.get("data") if isinstance(payload, dict) else None
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
        mappings_url = f"{KITSU_API_BASE}/anime/{kitsu_id}/mappings"
        r_map = requests.get(mappings_url, headers={"User-Agent": COMMON_HEADERS["User-Agent"]}, timeout=10)
        if r_map.status_code == 200:
            payload = r_map.json()
            data = payload.get("data") if isinstance(payload, dict) else []
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

    return {
        "titles": unique_titles,
        "mal_id": mal_id,
        "anilist_id": anilist_id,
    }

def _fetch_aniways_search_page(query, page=1, items_per_page=20):
    params = {
        "q": query,
        "page": page,
        "itemsPerPage": items_per_page,
    }
    try:
        r = requests.get(
            f"{ANIWAYS_API_BASE}/anime/listings/search",
            headers=ANIWAYS_COMMON_HEADERS,
            params=params,
            timeout=10
        )
        if r.status_code != 200:
            return []
        payload = r.json()
        items = payload.get("items") if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []
    except Exception:
        return []

@lru_cache(maxsize=1024)
def resolve_aniways_id_from_kitsu(kitsu_id):
    """Resolve Aniways anime id from a Kitsu anime id using mappings + title search."""
    ctx = get_kitsu_anime_context(kitsu_id)
    titles = ctx.get("titles") or []
    mal_id = ctx.get("mal_id")
    anilist_id = ctx.get("anilist_id")
    if not titles:
        return None

    # First pass: exact external-id match (most reliable)
    for title in titles[:6]:
        items = _fetch_aniways_search_page(title, page=1, items_per_page=20)
        for item in items:
            item_mal = item.get("malId")
            item_anilist = item.get("anilistId")
            if mal_id is not None and item_mal == mal_id:
                return item.get("id")
            if anilist_id is not None and item_anilist == anilist_id:
                return item.get("id")

    # Second pass: title similarity fallback.
    normalized_titles = {_normalize_title_for_match(t) for t in titles if t}
    for title in titles[:4]:
        items = _fetch_aniways_search_page(title, page=1, items_per_page=20)
        for item in items:
            names = [
                item.get("ename"),
                item.get("jname"),
            ]
            for name in names:
                if _normalize_title_for_match(name) in normalized_titles:
                    return item.get("id")

    return None

@app.route('/')
@app.route('/configure')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    manifest_data = dict(MANIFEST)
    logo = manifest_data.get("logo")
    if isinstance(logo, str) and logo.startswith("/"):
        base = request.url_root.rstrip("/")
        manifest_data["logo"] = f"{base}{logo}"
    return jsonify(manifest_data)

@app.route('/stream/<type>/<path:id>.json')
def stream(type, id):
    # Stremio format: tt1234567[:season:episode] (may be URL-encoded)
    decoded_id = _decode_stream_id(id)
    parts = [p for p in decoded_id.split(':') if p]
    imdb_id = parts[0] if parts else ""
    kind = (type or "").lower()
    season = _normalize_episode_part(parts[1] if len(parts) > 1 else None)
    episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)

    if imdb_id.lower() in ("aniways", "kitsu"):
        source_prefix = imdb_id.lower()
        source_id = parts[1] if len(parts) > 1 else None
        if len(parts) > 3:
            aniways_episode = _normalize_episode_part(parts[3])
        else:
            aniways_episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)

        if not source_id or not aniways_episode:
            return jsonify({"streams": []})

        anime_id = source_id
        if source_prefix == "kitsu":
            anime_id = resolve_aniways_id_from_kitsu(source_id)

        if not anime_id:
            return jsonify({"streams": []})

        aniways_streams = fetch_aniways_streams(anime_id, aniways_episode)
        aniways_streams.sort(key=lambda s: (str(s.get("name", "")), str(s.get("title", ""))))
        aniways_streams.append({
            "name": "Flix-Streams",
            "title": "Support development on Ko-fi",
            "externalUrl": "https://ko-fi.com/sandortoth",
        })
        return jsonify({"streams": aniways_streams})

    if not imdb_id.startswith("tt"):
        return jsonify({"streams": []})

    tmdb_id = get_tmdb_id(imdb_id, kind)
    if not tmdb_id:
        return jsonify({"streams": []})

    if kind in ("series", "tv") and (not season or not episode):
        _, hint_season, hint_episode = get_series_context_from_imdb(imdb_id)
        if not season and hint_season is not None:
            season = str(hint_season)
        if not episode and hint_episode is not None:
            episode = str(hint_episode)

    if kind in ("series", "tv") and (not season or not episode):
        return jsonify({"streams": []})

    all_streams = []
    decryption_key = get_decryption_key()
    if decryption_key:
        # VidZee provider
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(
                lambda s: fetch_server_streams(tmdb_id, s, season, episode, decryption_key),
                SERVERS
            )
            for res in results:
                all_streams.extend(res)
    else:
        app.logger.warning("VidZee decryption key unavailable; skipping VidZee provider")

    # AutoEmbed provider
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(
            lambda s: fetch_autoembed_server_streams(tmdb_id, s, season, episode),
            AUTOEMBED_SERVERS
        )
        for res in results:
            all_streams.extend(res)

    # Keep provider groups stable in the list (VidZee first, AutoEmbed second).
    def _provider_rank(stream_obj):
        name = str(stream_obj.get("name", "")).lower()
        if name.startswith("vidzee"):
            return 0
        if name.startswith("autoembed"):
            return 1
        if name.startswith("aniways"):
            return 2
        return 3

    all_streams.sort(key=lambda s: (_provider_rank(s), str(s.get("name", "")), str(s.get("title", ""))))

    # Keep a clickable support link as the final item in the stream list.
    all_streams.append({
        "name": "Flix-Streams",
        "title": "Support development on Ko-fi",
        "externalUrl": "https://ko-fi.com/sandortoth",
    })

    return jsonify({"streams": all_streams})

if __name__ == '__main__':
    # Use environment variable for port, default to 7000
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port)
