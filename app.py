import json
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
    "version": "1.0.22",
    "name": "Flix-Streams",
    "description": "Stream movies and series from VidZee and AutoEmbed.",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
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

@app.route('/')
@app.route('/configure')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return jsonify(MANIFEST)

@app.route('/stream/<type>/<path:id>.json')
def stream(type, id):
    # Stremio format: tt1234567[:season:episode] (may be URL-encoded)
    decoded_id = _decode_stream_id(id)
    parts = [p for p in decoded_id.split(':') if p]
    imdb_id = parts[0] if parts else ""
    kind = (type or "").lower()
    season = _normalize_episode_part(parts[1] if len(parts) > 1 else None)
    episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)

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
        return 2

    all_streams.sort(key=lambda s: (_provider_rank(s), str(s.get("name", "")), str(s.get("title", ""))))

    return jsonify({"streams": all_streams})

if __name__ == '__main__':
    # Use environment variable for port, default to 7000
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port)
