import os
import re
import json
import base64
import hashlib
import time
import requests
from urllib.parse import unquote
from functools import lru_cache
from flask import Flask, jsonify, render_template
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
    "version": "1.0.2",
    "name": "Flix-Streams",
    "description": "Stream movies and TV shows from Flix-Streams (VidZee).",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt", "tmdb"],
    "catalogs": []
}

SERVERS = [
    {"id": "2", "name": "Glory"},
    {"id": "3", "name": "Server 3"},
    {"id": "7", "name": "Server 7"},
    {"id": "9", "name": "Hindi"},
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://test.autoembed.cc/",
    "Origin": "https://test.autoembed.cc"
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


def decrypt_response(data_json):
    """Decrypts the AutoEmbed API response using PBKDF2 and AES-CBC."""
    try:
        if "data" in data_json:
             inner_json_str = base64.b64decode(data_json["data"]).decode('utf-8')
             data_json = json.loads(inner_json_str)

        key_hex = data_json['key']
        iv_hex = data_json['iv']
        salt_hex = data_json['salt']
        iterations = data_json['iterations']
        encrypted_data_b64 = data_json['encryptedData']

        salt = bytes.fromhex(salt_hex)
        iv = bytes.fromhex(iv_hex)
        encrypted_data = base64.b64decode(encrypted_data_b64)

        key = PBKDF2(key_hex, salt, dkLen=32, count=iterations, hmac_hash_module=SHA256)

        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as e:
        app.logger.error(f"Decryption failed: {e}")
        return None

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

def fetch_server_streams(tmdb_id, sr_info, season, episode):
    """Worker function to fetch streams from a specific server."""
    sr = sr_info["id"]
    api_url = f"https://test.autoembed.cc/api/server?id={tmdb_id}&sr={sr}"

    # Determine Referer
    if season and episode:
        api_url += f"&ss={season}&ep={episode}"
        referer = f"https://test.autoembed.cc/embed/tv/{tmdb_id}/{season}/{episode}"
    else:
        referer = f"https://test.autoembed.cc/embed/movie/{tmdb_id}"

    headers = COMMON_HEADERS.copy()
    headers["Referer"] = referer

    streams = []
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        decrypted_data = decrypt_response(data)
        if not decrypted_data:
            return []

        # Parse subtitles from decrypted data
        raw_subs = decrypted_data.get("tracks", []) or decrypted_data.get("subtitles", [])
        subtitles = parse_subtitles(raw_subs)

        # Stream URL
        stream_url = decrypted_data.get("url")
        if stream_url:
             stream_obj = {
                "name": f"AutoEmbed - {sr_info['name']}",
                "title": f"Server {sr_info['name']}",
                "url": stream_url,
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

    all_streams = []
    # Increase workers to ensure all server requests start immediately
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(
            lambda s: fetch_server_streams(tmdb_id, s, season, episode),
            SERVERS
        )
        for res in results:
            all_streams.extend(res)

    return jsonify({"streams": all_streams})

if __name__ == '__main__':
    # Use environment variable for port, default to 7000
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port)
