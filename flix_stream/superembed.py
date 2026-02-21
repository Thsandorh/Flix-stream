import re
import json
import base64
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from flix_stream.tmdb import get_imdb_id_from_tmdb

# Configuration for SuperEmbed
BASE_URL = "https://www.superembed.stream"
MULTIEMBED_URL = "https://multiembed.mov"
STREAMINGNOW_URL = "https://streamingnow.mov"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://multiembed.mov/",
    "Origin": "https://multiembed.mov"
}

def fetch_superembed_streams(tmdb_id, kind, season=None, episode=None):
    """
    Fetches streams from SuperEmbed by following the redirect chain and identifying direct M3U8 links.
    """
    streams = []
    imdb_id = get_imdb_id_from_tmdb(tmdb_id)
    if not imdb_id:
        return []

    # Construct the search URL for SuperEmbed/MultiEmbed
    if kind in ("series", "tv"):
        query_url = f"{MULTIEMBED_URL}/?video_id={imdb_id}&s={season}&e={episode}"
    else:
        query_url = f"{MULTIEMBED_URL}/?video_id={imdb_id}"

    try:
        # 1. Get the session token and follow initial redirect
        session = requests.Session()
        res = session.get(query_url, headers=HEADERS, timeout=10)

        # SuperEmbed uses a redirect to streamingnow.mov with a token
        if "streamingnow.mov" in res.url:
            target_url = res.url
        else:
            # Fallback: check for scripts or meta redirects
            match = re.search(r'window\.location\.href\s*=\s*"(https://streamingnow\.mov/[^"]+)"', res.text)
            if match:
                target_url = match.group(1)
            else:
                return []

        # 2. Get the server list from the streamingnow page
        # This typically involves a POST to response.php with the token
        token_match = re.search(r'var\s+token\s*=\s*"([^"]+)"', res.text)
        if not token_match:
            # Try getting the page content first if we haven't already
            res = session.get(target_url, headers=HEADERS, timeout=10)
            token_match = re.search(r'var\s+token\s*=\s*"([^"]+)"', res.text)

        if not token_match:
            return []

        token = token_match.group(1)

        # Fetch the server list
        response_url = f"{STREAMINGNOW_URL}/response.php"
        res = session.post(response_url, headers={**HEADERS, "Referer": target_url}, data={"token": token}, timeout=10)

        try:
            servers = res.json()
        except:
            return []

        # 3. Process each server to find direct links or embeds
        # Priority: Servers 88, 89, 90 often provide internal players with direct M3U8
        vip_server_ids = ["88", "89", "90"]

        def process_server(server):
            srv_id = str(server.get("id"))
            srv_name = server.get("name", f"Server {srv_id}")

            # Construct the play URL
            play_url = f"{STREAMINGNOW_URL}/playvideo.php?id={srv_id}&token={token}"

            # If it's a VIP server, try to extract the direct M3U8
            if srv_id in vip_server_ids:
                try:
                    srv_res = session.get(play_url, headers={**HEADERS, "Referer": target_url}, timeout=10)
                    # Check for direct M3U8 in Playerjs config
                    # Look for file: "..." or file: '...'
                    m3u8_match = re.search(r'file\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', srv_res.text)
                    if m3u8_match:
                        direct_url = m3u8_match.group(1)

                        # Extract subtitles if available
                        subtitles = []
                        subtitle_match = re.search(r'subtitle\s*:\s*["\']([^"\']+)["\']', srv_res.text)
                        if subtitle_match:
                            sub_str = subtitle_match.group(1)
                            # Format: [Lang]https://url.vtt,[Lang2]https://url2.vtt
                            sub_parts = sub_str.split(",")
                            for part in sub_parts:
                                if "[" in part and "]" in part:
                                    label = part[part.find("[")+1:part.find("]")]
                                    url = part[part.find("]")+1:]
                                    # Map common names to ISO 639-2
                                    lang_code = label.lower()[:3]
                                    if "eng" in lang_code: lang_code = "eng"
                                    elif "spa" in lang_code: lang_code = "spa"
                                    elif "fre" in lang_code: lang_code = "fre"
                                    elif "ger" in lang_code: lang_code = "deu"

                                    subtitles.append({
                                        "id": label,
                                        "url": url,
                                        "lang": lang_code
                                    })

                        return {
                            "name": f"SuperEmbed VIP-{srv_id}",
                            "title": f"[SuperEmbed] Direct M3U8 ({srv_id})\nSubtitles: {len(subtitles)}",
                            "url": direct_url,
                            "subtitles": subtitles,
                            "behaviorHints": {
                                "notWebReady": True,
                                "proxyHeaders": {
                                    "request": {
                                        "User-Agent": HEADERS["User-Agent"],
                                        "Referer": "https://player.vidzee.wtf/", # Common referer used in the app
                                        "Origin": "https://player.vidzee.wtf"
                                    }
                                }
                            }
                        }
                except:
                    pass

            # Fallback for other servers or if direct extraction failed
            return {
                "name": f"SuperEmbed {srv_name}",
                "title": f"[SuperEmbed] Server {srv_id}",
                "url": play_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": HEADERS["User-Agent"],
                            "Referer": target_url,
                            "Origin": STREAMINGNOW_URL
                        }
                    }
                }
            }

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(process_server, servers))
            streams.extend([r for r in results if r])

    except Exception as e:
        # Fail silently in production, or log it
        pass

    return streams
