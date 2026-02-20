import os
import re
import base64
import json
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
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0YzY4ZTRjYjBhMDM4OTk0MTliNmVmYTZiOGJjOGJiZSIsIm5iZiI6MTcyNzUwNjM2NS40NDQxNjUsInN1YiI6IjY2NWQ5YmMwYTVlMDU0MzUwMTQ5MWUwNSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.8OL7WQIZGWr9tRfmSkRFIsaf1Wy0ksrOGDCB4KcocW4")
MASTER_KEY = "b3f2a9d4c6e1f8a7b"

MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.0.2",
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

def extract_headers_from_proxy(proxy_url):
    """
    Extracts Referer and Origin headers from the proxyHls string (Aniways).
    Format is typically: /proxy/hd/{base64_headers}/{base64_url}
    """
    try:
        parts = proxy_url.split('/')
        for part in parts:
            if part.startswith('ey'):
                padding = len(part) % 4
                if padding:
                    part += '=' * (4 - padding)

                decoded_bytes = base64.b64decode(part)
                headers_json = json.loads(decoded_bytes)

                headers = {}
                if "referer" in headers_json:
                    headers["Referer"] = headers_json["referer"]
                if "origin" in headers_json:
                    headers["Origin"] = headers_json["origin"]
                return headers
    except Exception as e:
        app.logger.error(f"Error parsing proxy headers: {e}")
    return {}

@lru_cache(maxsize=2048)
def get_tmdb_id(imdb_id, content_type=None):
    """Maps IMDB ID to TMDB ID using the TMDB API.

    For series requests Stremio can sometimes pass episode-level IMDb IDs.
    In that case TMDB responds with ``tv_episode_results`` instead of
    ``tv_results``. We map those back to the parent show via ``show_id``.
    """
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
    return None

@lru_cache(maxsize=2048)
def get_series_context_from_imdb(imdb_id):
    """Resolves show/season/episode context from an IMDb episode id."""
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
    """Parses Stremio stream id and resolves TMDB id + season/episode.

    Supports IMDb ids (``tt...``) and TMDB-prefixed ids (``tmdb:...``),
    including episode forms such as ``tmdb:224372:1:1``.
    """
    decoded_id = _decode_stream_id(raw_id)
    parts = [token for token in re.split(r'[:/]', decoded_id) if token]

    # IMDb format: tt1234567[:season:episode]
    if parts and parts[0].startswith('tt'):
        imdb_id = parts[0]
        season, episode = _extract_season_episode(parts[1:])
        tmdb_id = get_tmdb_id(imdb_id, content_type)
        kind = (content_type or "").lower()

        if kind in ("series", "tv") and (not season or not episode or not tmdb_id):
            hint_tmdb_id, hint_season, hint_episode = get_series_context_from_imdb(imdb_id)
            if not tmdb_id:
                tmdb_id = hint_tmdb_id
            if not season and hint_season is not None:
                season = str(hint_season)
            if not episode and hint_episode is not None:
                episode = str(hint_episode)

        return tmdb_id, season, episode

    # TMDB format variants:
    # - tmdb:224372[:season:episode]
    # - tmdb:tv:224372[:season:episode]
    # - tmdb:series:224372[:season:episode]
    # - tmdb:movie:12345
    if parts and parts[0].lower() == 'tmdb':
        tmdb_id = None
        season = None
        episode = None

        # Find first numeric segment as TMDB id, then read season/episode after it.
        for i, token in enumerate(parts[1:], start=1):
            if token.isdigit():
                tmdb_id = int(token)
                season, episode = _extract_season_episode(parts[i + 1:])
                break

        return tmdb_id, season, episode

    # Fallback TMDB-like variants without explicit "tmdb" prefix:
    # - 224372[:season:episode]
    # - tv:224372[:season:episode]
    # - series:224372[:season:episode]
    # - movie:12345
    if parts and (parts[0].isdigit() or parts[0].lower() in ("tv", "series", "movie")):
        tmdb_id = None
        season = None
        episode = None

        for i, token in enumerate(parts):
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
                    stream_obj = {
                        "name": f"Flicky - {sr_info['name']}",
                        "title": f"{u.get('lang', 'English')} {u.get('message', '')}\n{u.get('name', '')}",
                        "url": decrypted_url,
                        "behaviorHints": {
                            "notWebReady": True,
                            "proxyHeaders": {
                                "request": COMMON_HEADERS
                            }
                        }
                    }
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
    tmdb_id, season, episode = parse_stream_id(type, id)
    app.logger.info(
        "stream request type=%s id=%s parsed_tmdb=%s season=%s episode=%s",
        type, id, tmdb_id, season, episode
    )
    if not tmdb_id:
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

    all_streams = []
    # Increase workers to ensure all server requests start immediately
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(
            lambda s: fetch_server_streams(tmdb_id, s, season, episode, decryption_key),
            SERVERS
        )
        for res in results:
            all_streams.extend(res)

    return jsonify({"streams": all_streams})

if __name__ == '__main__':
    # Use environment variable for port, default to 7000
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port)
