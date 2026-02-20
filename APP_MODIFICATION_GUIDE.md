# Required Modifications for `app.py`

To fully support Aniways streaming, you need to add logic to your main `app.py` file. This logic decodes the "unreadable" Base64 proxy headers (`proxyHls`) and provides Stremio with a clean `.m3u8` link plus the necessary authorization headers (`Referer`, `Origin`, `User-Agent`) required for playback.

**Goal:** The user will see a playable stream in Stremio. The "unreadable text" is processed internally and converted into valid HTTP headers.

## 1. Add Imports
At the top of `app.py`, ensure you have imported the `json` module. It is required to parse the decoded headers.

```python
import os
import re
import base64
import json  # <--- Add this line
import hashlib
import time
# ... (rest of imports)
```

## 2. Add Helper Functions
Add these two functions to `app.py` (e.g., before `get_tmdb_id`).

### A. Header Decoder
This function takes the "garbage" `proxyHls` string and extracts the clean headers. It also explicitly adds the User-Agent to ensure stricter servers (like Megaplay) accept the connection.

```python
def extract_headers_from_proxy(proxy_url):
    """
    Extracts Referer and Origin headers from the proxyHls string (Aniways).
    Format is typically: /proxy/hd/{base64_headers}/{base64_url}
    """
    try:
        # Split by '/' and find the segment starting with 'ey' (base64 for JSON '{')
        parts = proxy_url.split('/')
        for part in parts:
            if part.startswith('ey'):
                # Add padding if necessary for base64 decoding
                padding = len(part) % 4
                if padding:
                    part += '=' * (4 - padding)

                decoded_bytes = base64.b64decode(part)
                headers_json = json.loads(decoded_bytes)

                # Normalize keys to title case if needed
                headers = {}
                if "referer" in headers_json:
                    headers["Referer"] = headers_json["referer"]
                if "origin" in headers_json:
                    headers["Origin"] = headers_json["origin"]

                # IMPORTANT: Always ensure a valid User-Agent is present
                # This is critical for servers like Megaplay/Rapid-Cloud
                headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

                return headers
    except Exception as e:
        app.logger.error(f"Error parsing proxy headers: {e}")
    return {}
```

### B. Fetch Logic (The "Worker")
This function fetches the actual stream link from Aniways. You will call this inside your main `/stream` route logic.

```python
def fetch_aniways_stream(anime_id, episode_num):
    """
    Fetches stream information from Aniways.xyz for a specific episode.
    """
    API_BASE = "https://api.aniways.xyz"
    # Aniways requires specific headers to look like a browser
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://aniways.xyz/",
        "Origin": "https://aniways.xyz"
    }

    try:
        # 1. Get Episodes List to find the internal ID
        r_ep = requests.get(f"{API_BASE}/anime/{anime_id}/episodes", headers=HEADERS, timeout=10)
        if r_ep.status_code != 200: return []

        episodes = r_ep.json()
        target_ep = next((ep for ep in episodes if str(ep.get("number")) == str(episode_num)), None)
        if not target_ep: return []

        episode_id = target_ep["id"]

        # 2. Get Servers for the Episode
        r_srv = requests.get(f"{API_BASE}/anime/{anime_id}/episodes/{episode_id}/servers", headers=HEADERS, timeout=10)
        if r_srv.status_code != 200: return []

        servers = r_srv.json()
        streams = []

        for srv in servers:
            server_id = srv.get("serverId")
            server_name = srv.get("serverName")
            server_type = srv.get("type")

            # 3. Fetch the Stream URL
            # REQUIRED PARAMS: server (lowercase, hyphenated) and type
            params = {
                "server": server_name.lower().replace(" ", "-") if server_name else "",
                "type": server_type.lower() if server_type else ""
            }

            try:
                r_stream = requests.get(f"{API_BASE}/anime/{anime_id}/episodes/servers/{server_id}", headers=HEADERS, params=params, timeout=5)
                if r_stream.status_code == 200:
                    data = r_stream.json()
                    source = data.get("source", {})

                    if "hls" in source:
                        hls_url = source["hls"]
                        proxy_hls = source.get("proxyHls", "")

                        # DECODE THE HEADERS HERE
                        stream_headers = extract_headers_from_proxy(proxy_hls)

                        # Create Stremio stream object
                        streams.append({
                            "name": f"Aniways - {server_name}",
                            "title": f"Server {server_name}",
                            "url": hls_url,  # The CLEAN url
                            "behaviorHints": {
                                "notWebReady": True,
                                "proxyHeaders": {
                                    "request": stream_headers  # The DECODED headers (Referer, Origin, UA)
                                }
                            }
                        })
            except Exception as e:
                app.logger.error(f"Error fetching stream for server {server_name}: {e}")

        return streams
    except Exception as e:
        app.logger.error(f"Error in fetch_aniways_stream: {e}")
        return []
```

## 3. Integration in `/stream`
Finally, inside the `stream` route handler (`def stream(type, id):`), call the new function. Since `app.py` uses TMDB IDs, you will need a way to map the incoming ID to an Aniways ID (which is usually a hash like `8698ca...`).

*Note: Mapping logic (TMDB -> Aniways ID) is not included here as it requires searching the Aniways API first.*

```python
# Inside stream() function...
if "aniways_id" in context:  # Assuming you found the ID
    aniways_streams = fetch_aniways_stream(aniways_id, episode)
    all_streams.extend(aniways_streams)
```
