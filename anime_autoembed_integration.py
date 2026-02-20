import json
import base64
import requests
import re
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Util.Padding import unpad

# Common Headers
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://anime.autoembed.cc/",
    "Origin": "https://anime.autoembed.cc"
}

def decrypt_response(data_json):
    """
    Decrypts the AutoEmbed API response using PBKDF2 and AES-CBC.
    Shared logic with movie/tv integration.
    """
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

def fetch_anime_stream(title_slug, episode_num):
    """
    Fetches the stream for an anime episode from AutoEmbed.cc.

    Args:
        title_slug: The slug of the anime title (e.g., 'one-piece', 'naruto-shippuuden').
                    Note: The exact format depends on AutoEmbed's internal mapping.
                    Usually matches the URL slug.
        episode_num: The episode number.

    Returns:
        List of stream objects or None if failed.
    """
    # Construct Embed URL
    # Format: https://anime.autoembed.cc/embed/{title}-episode-{episode}
    embed_url = f"https://anime.autoembed.cc/embed/{title_slug}-episode-{episode_num}"
    print(f"Fetching embed: {embed_url}")

    try:
        # Step 1: Get the embed page to find server info
        r = requests.get(embed_url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()

        # Note: The Anime API documentation suggests a simple embed URL.
        # However, typically you need to call an API endpoint to get the actual stream.
        # Based on Movie/TV logic, it might be: https://anime.autoembed.cc/api/server
        # But we need the 'id' (AutoEmbed internal ID) first, which might be in the HTML.

        # Hypothetical extraction of ID from embed page
        # Look for something like: var id = "..." or data-id="..."
        anime_id = None
        match = re.search(r'data-id="([^"]+)"', r.text)
        if match:
            anime_id = match.group(1)

        if not anime_id:
            # Fallback: regex for JS variable
            match = re.search(r'var\s+id\s*=\s*["\']([^"\']+)["\']', r.text)
            if match:
                anime_id = match.group(1)

        if not anime_id:
            print("Could not extract Anime ID from embed page. The page might require JS execution or structure changed.")
            # In some cases, the ID in the URL IS the ID used for the API,
            # or the API accepts the slug directly.
            # Let's assume we might need to try the slug as ID if extraction fails,
            # though usually numeric IDs are expected.
            anime_id = f"{title_slug}-episode-{episode_num}"

        print(f"Using Anime ID: {anime_id}")

        # Step 2: Call Server API
        # Iterating through common server IDs found in AutoEmbed ecosystem
        # 1: Gogoanime, 2: Vidstream, etc. (Hypothetical mapping)
        streams = []
        server_ids = ["1", "2", "3", "4"]

        for sr in server_ids:
            # API Endpoint assumption based on main site structure
            api_url = f"https://anime.autoembed.cc/api/server?id={anime_id}&sr={sr}"

            headers = COMMON_HEADERS.copy()
            headers["Referer"] = embed_url

            try:
                r_api = requests.get(api_url, headers=headers, timeout=5)
                if r_api.status_code != 200:
                    continue

                data = r_api.json()
                decrypted = decrypt_response(data)

                if decrypted and decrypted.get("url"):
                    print(f"Found stream on server {sr}")
                    streams.append({
                        "server": sr,
                        "url": decrypted["url"],
                        "headers": headers
                    })
            except Exception as e:
                print(f"Error fetching server {sr}: {e}")

        return streams

    except Exception as e:
        print(f"Error fetching anime stream: {e}")
        return None

if __name__ == "__main__":
    # Example usage (Unverified due to connection timeouts in sandbox)
    fetch_anime_stream("one-piece", "1")
