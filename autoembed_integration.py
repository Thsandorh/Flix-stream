import json
import base64
import requests
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Util.Padding import unpad
from concurrent.futures import ThreadPoolExecutor

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
        print(f"Decryption failed: {e}")
        return None

def fetch_server_streams(tmdb_id, sr_info, season, episode, parse_subtitles_func):
    """
    Worker function to fetch streams from a specific server.

    Args:
        tmdb_id: The TMDB ID of the content.
        sr_info: Dictionary containing server 'id' and 'name'.
        season: Season number (string) or None.
        episode: Episode number (string) or None.
        parse_subtitles_func: Function to parse subtitles (use existing one).
    """
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
        subtitles = parse_subtitles_func(raw_subs)

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
        print(f"Error fetching streams for server {sr}: {e}")
    return streams
