import gzip
import io
import json
import logging
import re
from functools import lru_cache
from urllib.parse import quote

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

        try:
            content = gzip.decompress(response.content)
        except gzip.BadGzipFile:
            content = response.content

        data = json.loads(content)
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
    match = re.search(r'/embed/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    # Also handle regular watch URLs if present
    match = re.search(r'v=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def _wrap_text(text, max_len=20):
    words = text.split()
    lines = []
    current_line = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > max_len:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)

def _generate_poster(name, country_code):
    # Wrap text for better visibility on dummy image
    wrapped_name = _wrap_text(name, max_len=18)
    encoded_name = quote(wrapped_name)
    # Using 1a1a1a background and FFF text
    return f"https://placehold.co/600x900/1a1a1a/FFF.jpg?text={encoded_name}"

def get_famelack_catalog(code, skip=0):
    channels = fetch_famelack_country(code)
    if not channels:
        return []

    # Filter out channels that have NO streams at all (IPTV or YouTube)
    valid_channels = [
        ch for ch in channels
        if ch.get("iptv_urls") or ch.get("youtube_urls")
    ]
    valid_channels.sort(key=lambda x: x.get("name", ""))

    page_size = 100
    start = skip
    end = start + page_size
    paged_channels = valid_channels[start:end]

    metas = []
    for ch in paged_channels:
        nanoid = ch.get("nanoid")
        name = ch.get("name")
        country_code = ch.get("country", "").lower()

        # Always use generated poster with channel name
        poster = _generate_poster(name, country_code)

        metas.append({
            "id": f"famelack:{country_code}:{nanoid}",
            "type": "series",
            "name": name,
            "poster": poster,
            "description": f"Country: {country_code.upper()}", # Removed Source: Famelack prefix
            "background": poster,
            "behaviorHints": {
                "defaultVideoId": f"famelack:{country_code}:{nanoid}"
            }
        })

    return metas

def get_famelack_meta(famelack_id):
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

    # Always use generated poster with channel name
    poster = _generate_poster(name, country_code)

    return {
        "id": famelack_id,
        "type": "series",
        "name": name,
        "poster": poster,
        "background": poster,
        "description": f"Watch {name} live.\n\nCountry: {country_code.upper()}", # Removed Source: Famelack
        "genres": ["Live TV", country_code.upper()],
        "country": country_code.upper(),
        "videos": [
            {
                "id": famelack_id,
                "title": "Live Stream",
                "season": 1,
                "episode": 1,
                "released": "2024-01-01T00:00:00.000Z",
            }
        ],
        "behaviorHints": {
            "defaultVideoId": famelack_id
        }
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

    # Add IPTV streams
    iptv_urls = channel.get("iptv_urls", [])
    for i, url in enumerate(iptv_urls):
        stream_name = f"IPTV {i+1}"
        if len(iptv_urls) == 1 and not channel.get("youtube_urls"):
            stream_name = "Live TV"

        streams.append({
            "name": channel.get("name"),
            "title": stream_name,
            "url": url,
            "behaviorHints": {
                "notWebReady": True
            }
        })

    # Add YouTube streams
    youtube_urls = channel.get("youtube_urls", [])
    for i, url in enumerate(youtube_urls):
        yt_id = _extract_youtube_id(url)
        if yt_id:
            streams.append({
                "name": "YouTube",
                "title": f"Stream {i+1}",
                "ytId": yt_id
            })
        else:
            streams.append({
                "name": "YouTube (Link)",
                "title": f"Stream {i+1}",
                "url": url
            })

    return streams
