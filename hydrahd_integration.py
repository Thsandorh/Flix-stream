import requests
import re
from urllib.parse import urlparse

# Common headers for requests
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://hydrahd.ru/",
    "Origin": "https://hydrahd.ru"
}

def get_hydrahd_streams(imdb_id, tmdb_id, season=None, episode=None):
    """
    Fetches stream links from HydraHD.
    Currently only supports movies as verified endpoint is ajax/mov_0.php.
    """
    if season or episode:
        return []

    streams = []
    try:
        url = "https://hydrahd.ru/ajax/mov_0.php"
        params = {
            "i": imdb_id,
            "t": tmdb_id
        }

        # HydraHD requires a Referer, and generic 'https://hydrahd.ru/' works.
        response = requests.get(url, params=params, headers=COMMON_HEADERS, timeout=10)
        if response.status_code != 200:
            return []

        # Parse HTML for data-link
        # Format: <div class="iframe-server-button " data-id="10" data-link="..." onclick="...">
        # We use regex to find all data-link attributes.
        links = re.findall(r'data-link="([^"]+)"', response.text)

        seen_links = set()

        for link in links:
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            # Basic validation
            if not link.startswith("http"):
                continue

            # Determine a name for the stream based on the domain
            parsed = urlparse(link)
            domain = parsed.netloc.replace("www.", "")

            name = f"HydraHD - {domain}"
            title = f"Stream from {domain}\nEmbed URL"

            # Special handling for known providers to make the name nicer
            if "autoembed" in domain:
                name = "HydraHD - AutoEmbed"
            elif "vidsrc" in domain:
                name = "HydraHD - VidSrc"
            elif "frembed" in domain:
                name = "HydraHD - Frembed"
            elif "vidup" in domain:
                name = "HydraHD - VidUp"
            elif "ythd" in domain:
                name = "HydraHD - YTHD"

            stream_obj = {
                "name": name,
                "title": title,
                "url": link,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {
                        "request": {
                            "Referer": "https://hydrahd.ru/",
                            "User-Agent": COMMON_HEADERS["User-Agent"]
                        }
                    }
                }
            }
            streams.append(stream_obj)

    except Exception as e:
        # In a real app we might log this, but for now we print or ignore.
        # Since app.py has a logger, we can't easily access it here without circular imports or passing it.
        # We'll just return empty list on error.
        pass

    return streams
