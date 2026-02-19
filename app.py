import os
import base64
import hashlib
import requests
from flask import Flask, jsonify, render_template
from Crypto.Cipher import AES
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Config
# For a production addon, these should be moved to environment variables.
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0YzY4ZTRjYjBhMDM4OTk0MTliNmVmYTZiOGJjOGJiZSIsIm5iZiI6MTcyNzUwNjM2NS40NDQxNjUsInN1YiI6IjY2NWQ5YmMwYTVlMDU0MzUwMTQ5MWUwNSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.8OL7WQIZGWr9tRfmSkRFIsaf1Wy0ksrOGDCB4KcocW4")
MASTER_KEY = "b3f2a9d4c6e1f8a7b"

MANIFEST = {
    "id": "org.flickystream.addon",
    "version": "1.0.0",
    "name": "Flix-Streams",
    "description": "Stream movies and TV shows from Flix-Streams (VidZee).",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
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

def get_decryption_key():
    """Fetches and decrypts the current VidZee API key."""
    try:
        r = requests.get("https://core.vidzee.wtf/api-key", timeout=10)
        r.raise_for_status()
        encrypted_data = base64.b64decode(r.text.strip())

        if len(encrypted_data) <= 28:
            return None

        iv = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        key = hashlib.sha256(MASTER_KEY.encode()).digest()
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
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

def get_tmdb_id(imdb_id):
    """Maps IMDB ID to TMDB ID using the TMDB API."""
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("movie_results"):
            return data["movie_results"][0]["id"]
        if data.get("tv_results"):
            return data["tv_results"][0]["id"]
    except Exception as e:
        app.logger.error(f"TMDB mapping failed for {imdb_id}: {e}")
    return None

def fetch_server_streams(tmdb_id, sr_info, season, episode, decryption_key):
    """Worker function to fetch streams from a specific server."""
    sr = sr_info["id"]
    api_url = f"https://player.vidzee.wtf/api/server?id={tmdb_id}&sr={sr}"
    if season and episode:
        api_url += f"&ss={season}&ep={episode}"

    streams = []
    try:
        r = requests.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("url"):
            for u in data["url"]:
                decrypted_url = decrypt_link(u["link"], decryption_key)
                if decrypted_url:
                    streams.append({
                        "name": f"Flicky - {sr_info['name']}",
                        "title": f"{u.get('lang', 'English')} {u.get('message', '')}\n{u.get('name', '')}",
                        "url": decrypted_url
                    })
    except Exception:
        pass
    return streams

@app.route('/')
@app.route('/configure')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return jsonify(MANIFEST)

@app.route('/stream/<type>/<id>.json')
def stream(type, id):
    # ID format: tt1234567:1:1
    parts = id.split(':')
    imdb_id = parts[0]
    season = parts[1] if len(parts) > 1 else None
    episode = parts[2] if len(parts) > 2 else None

    tmdb_id = get_tmdb_id(imdb_id)
    if not tmdb_id:
        return jsonify({"streams": []})

    decryption_key = get_decryption_key()
    if not decryption_key:
        return jsonify({"streams": []})

    all_streams = []
    with ThreadPoolExecutor(max_workers=5) as executor:
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
