import gzip
import io
import json
import logging
import re
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

FAMELACK_BASE_URL = "https://raw.githubusercontent.com/famelack/famelack-channels/main/channels/compressed"
METADATA_URL = f"{FAMELACK_BASE_URL}/countries_metadata.json"
CACHE_TTL = 3600  # 1 hour

@lru_cache(maxsize=1)
def get_famelack_countries():
    try:
        response = requests.get(METADATA_URL, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch metadata: {response.status_code}")
            return {}

        # Decompress if needed (GitHub raw usually serves gzip as application/octet-stream but requests might not auto-decompress unless content-encoding header is set correctly, which GitHub might not do for raw files)
        try:
            content = gzip.decompress(response.content)
        except gzip.BadGzipFile:
            content = response.content

        data = json.loads(content)
        # Filter only countries that have channels
        return {k: v for k, v in data.items() if v.get("hasChannels")}
    except Exception as e:
        logger.error(f"Error fetching famelack countries: {e}")
        return {}

@lru_cache(maxsize=20)
def fetch_famelack_country(code):
    code = code.lower()
    url = f"{FAMELACK_BASE_URL}/countries/{code}.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            # Try upper case just in case
            response = requests.get(f"{FAMELACK_BASE_URL}/countries/{code.upper()}.json", timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to fetch country {code}: {response.status_code}")
                return []

        try:
            content = gzip.decompress(response.content)
        except gzip.BadGzipFile:
            content = response.content

        return json.loads(content)
    except Exception as e:
        logger.error(f"Error fetching famelack country {code}: {e}")
        return []

def _extract_youtube_id(url):
    # simple extraction for embed links like https://www.youtube-nocookie.com/embed/VIDEO_ID
    match = re.search(r'/embed/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def get_famelack_catalog(code, skip=0):
    channels = fetch_famelack_country(code)
    if not channels:
        return []

    # Sort by name
    channels.sort(key=lambda x: x.get("name", ""))

    # Pagination
    page_size = 100 # Show more channels per page
    start = skip
    end = start + page_size
    paged_channels = channels[start:end]

    metas = []
    for ch in paged_channels:
        nanoid = ch.get("nanoid")
        name = ch.get("name")
        country_code = ch.get("country", "").lower()

        # Determine poster
        poster = None
        youtube_urls = ch.get("youtube_urls", [])
        if youtube_urls:
            yt_id = _extract_youtube_id(youtube_urls[0])
            if yt_id:
                poster = f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg"

        if not poster and country_code:
             poster = f"https://flagcdn.com/w320/{country_code}.png"

        metas.append({
            "id": f"famelack:{country_code}:{nanoid}",
            "type": "series", # or "tv"
            "name": name,
            "poster": poster,
            "description": f"Watch {name} from {country_code.upper()}",
            "background": poster
        })

    return metas

def get_famelack_meta(famelack_id):
    # id format: famelack:code:nanoid
    parts = famelack_id.split(":")
    if len(parts) != 3:
        return None

    code = parts[1]
    nanoid = parts[2]

    channels = fetch_famelack_country(code)
    channel = next((c for c in channels if c.get("nanoid") == nanoid), None)

    if not channel:
        return None

    name = channel.get("name")
    country_code = channel.get("country", "").lower()

    poster = None
    youtube_urls = channel.get("youtube_urls", [])
    if youtube_urls:
        yt_id = _extract_youtube_id(youtube_urls[0])
        if yt_id:
            poster = f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg"

    if not poster and country_code:
            poster = f"https://flagcdn.com/w320/{country_code}.png"

    return {
        "id": famelack_id,
        "type": "series",
        "name": name,
        "poster": poster,
        "background": poster,
        "description": f"Watch {name} live.",
        "genres": ["Live TV", country_code.upper()],
        "country": country_code.upper(),
        "videos": [
            {
                "id": famelack_id,
                "title": "Live Stream",
                "season": 1,
                "episode": 1,
            }
        ]
    }

def get_famelack_streams(famelack_id):
    parts = famelack_id.split(":")
    if len(parts) != 3:
        return []

    code = parts[1]
    nanoid = parts[2]

    channels = fetch_famelack_country(code)
    channel = next((c for c in channels if c.get("nanoid") == nanoid), None)

    if not channel:
        return []

    streams = []
    iptv_urls = channel.get("iptv_urls", [])

    for i, url in enumerate(iptv_urls):
        streams.append({
            "name": f"Stream {i+1}",
            "title": channel.get("name"),
            "url": url,
            "behaviorHints": {
                "notWebReady": True
            }
        })

    return streams
