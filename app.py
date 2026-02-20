import os
import re
import base64
import hashlib
import time
import requests
from urllib.parse import unquote
from functools import lru_cache
from flask import Flask, jsonify, render_template
from Crypto.Cipher import AES
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
TMDB_TOKEN = os.environ.get(
    "TMDB_TOKEN",
    "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0YzY4ZTRjYjBhMDM4OTk0MTliNmVmYTZiOGJjOGJiZSIsIm5iZiI6MTcyNzUwNjM2NS40NDQxNjUsInN1YiI6IjY2NWQ5YmMwYTVlMDU0MzUwMTQ5MWUwNSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.8OL7WQIZGWr9tRfmSkRFIsaf1Wy0ksrOGDCB4KcocW4",
)
MASTER_KEY = "b3f2a9d4c6e1f8a7b"

MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.0.14",
    "name": "Flix-Streams",
    "description": "Stream movies and TV shows from Flix-Streams (VidZee).",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt", "tmdb"],
    "catalogs": []
}

SERVERS = [
    {"id": "0", "name": "Nflix"},
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

STREAM_HEALTHCHECK_ENABLED = os.environ.get("STREAM_HEALTHCHECK", "1").lower() not in ("0", "false", "no")
try:
    STREAM_HEALTHCHECK_TIMEOUT = float(os.environ.get("STREAM_HEALTHCHECK_TIMEOUT", "2.5"))
except ValueError:
    STREAM_HEALTHCHECK_TIMEOUT = 2.5
STREAM_HEALTHCHECK_CACHE_TTL = 300

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
_HEALTH_CACHE = {}

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
    """Map IMDb id to TMDB id with type-aware selection."""
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
            if tv_results and tv_results[0].get("id"):
                return int(tv_results[0]["id"])
            if tv_episode_results and tv_episode_results[0].get("show_id"):
                return int(tv_episode_results[0]["show_id"])
            if tv_season_show_id:
                return int(tv_season_show_id)
            return None

        if kind == "movie":
            if movie_results and movie_results[0].get("id"):
                return int(movie_results[0]["id"])
            return None

        # Unknown type: best-effort fallback order.
        if movie_results:
            return movie_results[0].get("id")
        if tv_results:
            return tv_results[0].get("id")
        if tv_episode_results and tv_episode_results[0].get("show_id"):
            return tv_episode_results[0].get("show_id")
        if tv_season_show_id:
            return tv_season_show_id
    except Exception as e:
        app.logger.error(f"TMDB mapping failed for {imdb_id}: {e}")

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
            episode_info = tv_episode_results[0]
            return (
                episode_info.get("show_id"),
                episode_info.get("season_number"),
                episode_info.get("episode_number"),
            )

        tv_season_results = data.get("tv_season_results") or []
        if tv_season_results:
            season_info = tv_season_results[0]
            return (
                season_info.get("show_id"),
                season_info.get("season_number"),
                None,
            )
    except Exception as e:
        app.logger.error(f"TMDB series context lookup failed for {imdb_id}: {e}")

    return None, None, None

def _extract_season_episode(tokens):
    """Extract season/episode from tokenized id tail."""
    if not tokens:
        return None, None

    season = None
    episode = None
    cleaned = [str(token).strip() for token in tokens if str(token).strip()]
    lowered = [token.lower() for token in cleaned]

    for token in lowered:
        m = re.fullmatch(r"s(\d+)e(\d+)", token)
        if m:
            return m.group(1), m.group(2)

    for token in lowered:
        m = re.fullmatch(r"s(\d+)", token)
        if m and not season:
            season = m.group(1)
        m = re.fullmatch(r"e(?:p)?(\d+)", token)
        if m and not episode:
            episode = m.group(1)

    for idx, token in enumerate(lowered[:-1]):
        next_token = lowered[idx + 1]
        if token in ("s", "ss", "season") and next_token.isdigit() and not season:
            season = next_token
        if token in ("e", "ep", "episode") and next_token.isdigit() and not episode:
            episode = next_token

    if season and episode:
        return season, episode

    numeric_tokens = [token for token in lowered if token.isdigit()]
    if not season and numeric_tokens:
        season = numeric_tokens[0]
    if not episode and len(numeric_tokens) > 1:
        episode = numeric_tokens[1]

    return season, episode

def _normalize_episode_part(value):
    """Normalize season/episode values to plain integer strings."""
    if value is None:
        return None

    token = str(value).strip()
    if not token:
        return None

    if token.isdigit():
        return str(int(token))

    match = re.search(r"\d+", token)
    if match:
        return str(int(match.group(0)))

    return None

def _format_size(size_bytes):
    if size_bytes is None:
        return None

    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return None

def _extract_size_from_headers(headers):
    content_range = headers.get("Content-Range", "")
    m = re.search(r"/(\d+)$", content_range)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None

    content_length = headers.get("Content-Length", "")
    if content_length.isdigit():
        size = int(content_length)
        if size > 1:
            return size
    return None

def _health_cache_get(url):
    cached = _HEALTH_CACHE.get(url)
    if not cached:
        return None
    if time.time() - cached["ts"] > STREAM_HEALTHCHECK_CACHE_TTL:
        _HEALTH_CACHE.pop(url, None)
        return None
    return cached["ok"], cached["size"]

def _health_cache_set(url, ok, size_bytes=None):
    _HEALTH_CACHE[url] = {"ok": bool(ok), "size": size_bytes, "ts": time.time()}

def _probe_stream_url(url, is_hls):
    if not STREAM_HEALTHCHECK_ENABLED:
        return True, None

    cached = _health_cache_get(url)
    if cached is not None:
        return cached

    timeout = (1.0, STREAM_HEALTHCHECK_TIMEOUT)

    mp4_header_variants = [
        {
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Referer": COMMON_HEADERS["Referer"],
            "Origin": COMMON_HEADERS["Origin"],
            "Range": "bytes=0-0",
        },
        {
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Range": "bytes=0-0",
        }
    ]

    hls_header_variants = [
        {
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Referer": COMMON_HEADERS["Referer"],
            "Origin": COMMON_HEADERS["Origin"],
        },
        {
            "User-Agent": COMMON_HEADERS["User-Agent"],
        }
    ]

    headers_to_try = hls_header_variants if is_hls else mp4_header_variants
    for headers in headers_to_try:
        response = None
        try:
            response = requests.get(
                url, headers=headers, stream=True, timeout=timeout, allow_redirects=True
            )

            if is_hls:
                if response.status_code != 200:
                    continue
                content_type = (response.headers.get("Content-Type") or "").lower()
                chunk = next(response.iter_content(chunk_size=2048), b"")
                body = chunk.decode(errors="ignore")
                ok = (
                    "mpegurl" in content_type
                    or "#EXTM3U" in body
                    or ".ts" in body
                    or ".m4s" in body
                )
                if ok:
                    _health_cache_set(url, True, None)
                    return True, None
            else:
                if response.status_code in (200, 206):
                    size_bytes = _extract_size_from_headers(response.headers)
                    _health_cache_set(url, True, size_bytes)
                    return True, size_bytes
        except Exception:
            pass
        finally:
            if response is not None:
                response.close()

    _health_cache_set(url, False, None)
    return False, None

def _needs_stremio_proxy(decrypted_url, is_mp4, is_hls):
    """Decide whether stream should be routed via Stremio local proxy."""
    if is_mp4:
        return False

    if not is_hls:
        return False

    lowered = decrypted_url.lower()

    # Avoid double-proxying URLs that are already proxy wrappers.
    # Stremio desktop proxy can fail on these with AspNetCore.Proxy errors.
    if "/proxy/m3u8/" in lowered:
        return False

    # 67streams typically requires anti-hotlink headers for HLS chunks.
    if "67streams.online/" in lowered:
        return True

    return False

def _decode_stream_id(raw_id):
    """Decode URL-encoded stream ids, including double-encoded variants."""
    decoded = str(raw_id or "")
    for _ in range(2):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded

def parse_stream_id(content_type, raw_id):
    """Parse Stremio id and resolve provider id + season/episode."""
    decoded_id = _decode_stream_id(raw_id)
    parts = [token for token in re.split(r'[:/]', decoded_id) if token]
    kind = (content_type or "").lower()

    # IMDb format: tt1234567[:season:episode]
    if parts and parts[0].startswith('tt'):
        imdb_id = parts[0]
        season, episode = _extract_season_episode(parts[1:])

        if kind == "movie":
            return imdb_id, season, episode

        tmdb_id = get_tmdb_id(imdb_id, kind)
        hint_show_id = None
        hint_season = None
        hint_episode = None

        if kind in ("series", "tv") and (not tmdb_id or not season or not episode):
            hint_show_id, hint_season, hint_episode = get_series_context_from_imdb(imdb_id)

        if kind in ("series", "tv"):
            if not season and hint_season is not None:
                season = str(hint_season)
            if not episode and hint_episode is not None:
                episode = str(hint_episode)

        if kind in ("series", "tv") and not tmdb_id and hint_show_id:
            tmdb_id = int(hint_show_id)

        return tmdb_id, season, episode

    # TMDB direct variants:
    # - tmdb:224372[:season:episode]
    # - tmdb/tv/224372/1/5
    if parts and parts[0].lower() == "tmdb":
        tmdb_id = None
        season = None
        episode = None

        for i, token in enumerate(parts[1:], start=1):
            if token.isdigit():
                tmdb_id = int(token)
                season, episode = _extract_season_episode(parts[i + 1:])
                break
        return tmdb_id, season, episode

    return None, None, None

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

def fetch_server_streams(content_id, sr_info, season, episode, decryption_key):
    """Worker function to fetch streams from a specific server."""
    sr = sr_info["id"]
    api_url = f"https://player.vidzee.wtf/api/server?id={content_id}&sr={sr}"
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
                    stream_type = str(u.get("type", "")).lower()
                    is_hls = stream_type == "hls" or decrypted_url.lower().endswith(".m3u8")
                    is_mp4 = ".mp4" in decrypted_url.lower()
                    reachable, size_bytes = _probe_stream_url(decrypted_url, is_hls=is_hls)
                    if not reachable:
                        app.logger.info("Skipping unreachable stream from server %s: %s", sr, decrypted_url)
                        continue

                    label = "MP4" if is_mp4 else ("HLS" if is_hls else (stream_type.upper() or "STREAM"))
                    size_label = _format_size(size_bytes)
                    info_label = f"{label} | {size_label}" if size_label else label

                    behavior_hints = {}
                    if _needs_stremio_proxy(decrypted_url, is_mp4=is_mp4, is_hls=is_hls):
                        behavior_hints = {
                            "notWebReady": True,
                            "proxyHeaders": {
                                "request": COMMON_HEADERS
                            }
                        }

                    stream_obj = {
                        "name": f"Flicky - {sr_info['name']}",
                        "title": f"{u.get('lang', 'English')} {u.get('message', '')} [{info_label}]\n{u.get('name', '')}",
                        "url": decrypted_url,
                    }
                    if behavior_hints:
                        stream_obj["behaviorHints"] = behavior_hints
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                    streams.append(stream_obj)
    except Exception as e:
        app.logger.error(f"Error fetching streams for server {sr}: {e}")
    return streams

@app.route('/')
@app.route('/configure')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return jsonify(MANIFEST)

@app.route('/stream/<type>/<path:id>.json')
def stream(type, id):
    content_id, season, episode = parse_stream_id(type, id)
    if not content_id:
        return jsonify({"streams": []})

    kind = (type or "").lower()
    season = _normalize_episode_part(season)
    episode = _normalize_episode_part(episode)
    if not season or not episode:
        season = None
        episode = None

    # VidZee TV endpoint requires season and episode.
    if kind in ("series", "tv") and (not season or not episode):
        app.logger.warning(
            "missing season/episode for series request type=%s id=%s", type, id
        )
        return jsonify({"streams": []})

    decryption_key = get_decryption_key()
    if not decryption_key:
        return jsonify({"streams": []})

    def collect_streams(request_id):
        collected = []
        # Increase workers to ensure all server requests start immediately
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(
                lambda s: fetch_server_streams(request_id, s, season, episode, decryption_key),
                SERVERS
            )
            for res in results:
                collected.extend(res)
        return collected

    all_streams = collect_streams(content_id)

    return jsonify({"streams": all_streams})

if __name__ == '__main__':
    # Use environment variable for port, default to 7000
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port)
