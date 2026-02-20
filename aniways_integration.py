import requests
import re
import json
import base64

# Headers imitating a browser
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://aniways.xyz/",
    "Origin": "https://aniways.xyz"
}

API_BASE = "https://api.aniways.xyz"

def extract_headers_from_proxy(proxy_url):
    """
    Extracts Referer and Origin headers from the proxyHls string.
    Format is typically: /proxy/hd/{base64_headers}/{base64_url}
    """
    try:
        # Split by '/' and find the segment starting with 'ey' (base64 for JSON '{')
        parts = proxy_url.split('/')
        for part in parts:
            if part.startswith('ey'):
                # Add padding if necessary
                padding = len(part) % 4
                if padding:
                    part += '=' * (4 - padding)

                decoded_bytes = base64.b64decode(part)
                headers_json = json.loads(decoded_bytes)

                # Normalize keys to title case if needed, but requests handles case-insensitivity
                headers = {}
                if "referer" in headers_json:
                    headers["Referer"] = headers_json["referer"]
                if "origin" in headers_json:
                    headers["Origin"] = headers_json["origin"]
                return headers
    except Exception as e:
        print(f"  Error parsing proxy headers: {e}")
    return {}

def fetch_aniways_stream(anime_id, episode_num):
    """
    Fetches stream information from Aniways.xyz

    Args:
        anime_id: The Aniways anime ID (e.g. '8698ca792a1g8ae48a0g3' for 'BanG Dream-chan')
        episode_num: Episode number (integer or string)

    Returns:
        List of stream objects or None if failed.
    """
    try:
        # Step 1: Get Episodes List
        print(f"Fetching episodes for Anime ID: {anime_id}")
        episodes_url = f"{API_BASE}/anime/{anime_id}/episodes"
        r_ep = requests.get(episodes_url, headers=COMMON_HEADERS, timeout=10)

        if r_ep.status_code != 200:
            print(f"Failed to fetch episodes: {r_ep.status_code}")
            return None

        episodes = r_ep.json()
        target_ep = None

        # Find the target episode by number
        for ep in episodes:
            if str(ep.get("number")) == str(episode_num):
                target_ep = ep
                break

        if not target_ep:
            print(f"Episode {episode_num} not found.")
            return None

        episode_id = target_ep["id"]
        print(f"Found Episode ID: {episode_id}")

        # Step 2: Get Servers for the Episode
        servers_url = f"{API_BASE}/anime/{anime_id}/episodes/{episode_id}/servers"
        print(f"Fetching servers: {servers_url}")

        r_srv = requests.get(servers_url, headers=COMMON_HEADERS, timeout=10)
        if r_srv.status_code != 200:
            print(f"Failed to fetch servers: {r_srv.status_code}")
            return None

        servers = r_srv.json()
        print(f"Found {len(servers)} servers.")

        streams = []
        for srv in servers:
            server_id = srv.get("serverId")
            server_name = srv.get("serverName")
            server_type = srv.get("type")
            print(f"Processing Server: {server_name} (ID: {server_id}, Type: {server_type})")

            # Step 3: Fetch Stream URL
            # Endpoint: /anime/{animeId}/episodes/servers/{serverId}
            # Query Params (reversed from JS):
            #   server: serverName.lower().replace(" ", "-")
            #   type: type.lower()

            stream_api_url = f"{API_BASE}/anime/{anime_id}/episodes/servers/{server_id}"
            params = {
                "server": server_name.lower().replace(" ", "-") if server_name else "",
                "type": server_type.lower() if server_type else ""
            }

            try:
                print(f"  Fetching: {stream_api_url} with params {params}")
                r_stream = requests.get(stream_api_url, headers=COMMON_HEADERS, params=params, timeout=5)
                print(f"  Status: {r_stream.status_code}")

                if r_stream.status_code == 200:
                    stream_data = r_stream.json()
                    print(f"  Response: {json.dumps(stream_data)}")

                    # Parse the nested source object
                    source_obj = stream_data.get("source")
                    if source_obj and "hls" in source_obj:
                        hls_url = source_obj["hls"]
                        proxy_hls = source_obj.get("proxyHls", "")

                        # Extract headers from proxyHls if available
                        stream_headers = {}
                        if proxy_hls:
                            stream_headers = extract_headers_from_proxy(proxy_hls)

                        streams.append({
                            "name": f"Aniways - {server_name}",
                            "url": hls_url,
                            "headers": stream_headers
                        })
                        print(f"  > Found stream: {hls_url[:50]}...")
                        print(f"    Required Headers: {stream_headers}")
                else:
                    print(f"  Failed to get stream from API: {r_stream.status_code} - {r_stream.text}")

            except Exception as e:
                print(f"  Error fetching stream: {e}")

        return streams

    except Exception as e:
        print(f"Error in Aniways integration: {e}")
        return None

if __name__ == "__main__":
    # Example: BanG Dream-chan (ID: 8698ca792a1g8ae48a0g3) Episode 1
    fetch_aniways_stream("8698ca792a1g8ae48a0g3", "1")
