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
        # Check if wrapped in "data" (some endpoints do this)
        if "data" in data_json and isinstance(data_json["data"], str):
             inner_json_str = base64.b64decode(data_json["data"]).decode('utf-8')
             data_json = json.loads(inner_json_str)

        key_hex = data_json.get('key')
        iv_hex = data_json.get('iv')
        salt_hex = data_json.get('salt')
        iterations = data_json.get('iterations')
        encrypted_data_b64 = data_json.get('encryptedData')

        if not all([key_hex, iv_hex, salt_hex, iterations, encrypted_data_b64]):
            print("Missing encryption parameters in JSON.")
            return None

        # Convert hex/base64 to bytes
        # Some fields might be hex strings of the bytes
        # Let's ensure types are correct. 'key' in JSON is usually the password for PBKDF2.
        # Wait, the JS logic typically uses 'key' as the password, 'salt' as salt.

        password = key_hex.encode('utf-8')
        salt = bytes.fromhex(salt_hex)
        iv = bytes.fromhex(iv_hex)
        encrypted_data = base64.b64decode(encrypted_data_b64)

        # Derive key
        key = PBKDF2(password, salt, dkLen=32, count=iterations, hmac_hash_module=SHA256)

        # Decrypt
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None

def fetch_server_streams(tmdb_id, sr_info, season=None, episode=None):
    """
    Worker function to fetch streams from a specific server.
    """
    sr = sr_info["id"]
    # Base API URL
    api_url = f"https://test.autoembed.cc/api/server?id={tmdb_id}&sr={sr}"

    # Determine Referer
    if season and episode:
        # For TV shows, parameters are usually ss and ep
        api_url += f"&ss={season}&ep={episode}"
        referer = f"https://test.autoembed.cc/embed/tv/{tmdb_id}/{season}/{episode}"
    else:
        referer = f"https://test.autoembed.cc/embed/movie/{tmdb_id}"

    headers = COMMON_HEADERS.copy()
    headers["Referer"] = referer

    print(f"Fetching from: {api_url}")
    streams = []
    try:
        r = requests.get(api_url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        # print(f"Raw response (truncated): {str(data)[:100]}...")

        decrypted_data = decrypt_response(data)
        if not decrypted_data:
            print("Failed to decrypt response.")
            return []

        # Stream URL
        # The structure of decrypted_data usually contains 'url' or 'source'
        # Let's print keys to be sure
        # print(f"Decrypted keys: {decrypted_data.keys()}")

        stream_url = decrypted_data.get("url") or decrypted_data.get("link")
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
             streams.append(stream_obj)
             print(f"Found stream: {stream_url}")
        else:
             print("No stream URL found in decrypted data.")

    except Exception as e:
        print(f"Error fetching streams for server {sr}: {e}")
    return streams

if __name__ == "__main__":
    # Test with a known movie (e.g., Sintel or similar open content, or just a popular one)
    # Using TMDB ID for 'Dune' (2021) -> 438631 or similar.
    # Let's try 550 (Fight Club)
    test_id = "550"
    print(f"Testing AutoEmbed fetch for Movie ID: {test_id}")

    for server in SERVERS:
        print(f"Testing Server: {server['name']} (ID: {server['id']})")
        fetch_server_streams(test_id, server)
        print("-" * 30)
