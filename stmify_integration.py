import re
import json
import requests
from flask import Blueprint, jsonify, request
from functools import lru_cache

stmify_bp = Blueprint('stmify', __name__)

STMIFY_BASE_URL = "https://stmify.com"
CDN_BASE_URL = "https://cdn.stmify.com"

# Common headers to mimic a browser
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": STMIFY_BASE_URL + "/",
    "Origin": STMIFY_BASE_URL
}

@stmify_bp.route('/catalog/series/stmify-live.json')
def stmify_catalog():
    try:
        skip = request.args.get("skip")
        if skip:
            skip = int(skip)
        else:
            skip = 0
    except:
        skip = 0

    page = (skip // 20) + 1
    metas = scrape_catalog_page(page)
    return jsonify({"metas": metas})

@stmify_bp.route('/catalog/series/stmify-live/skip=<int:skip>.json')
def stmify_catalog_pagination(skip):
    page = (skip // 20) + 1
    metas = scrape_catalog_page(page)
    return jsonify({"metas": metas})

@lru_cache(maxsize=32)
def scrape_catalog_page(page=1):
    """Scrapes the Stmify Live TV channel list page dynamically."""
    url = f"{STMIFY_BASE_URL}/live-tv/"
    if page > 1:
        url = f"{STMIFY_BASE_URL}/live-tv/page/{page}/"

    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        if r.status_code != 200:
            return []

        html = r.text
        metas = []
        items = html.split('class="archive-item"')
        for item in items[1:]:
            link_match = re.search(r'<a\s+href="([^"]+)"', item)
            if not link_match: continue
            link = link_match.group(1)

            slug_match = re.search(r'/live-tv/([^/]+)/', link)
            if not slug_match: continue
            slug = slug_match.group(1)

            img_match = re.search(r'<img[^>]+src="([^"]+)"', item)
            data_src_match = re.search(r'<img[^>]+data-src="([^"]+)"', item)

            poster = None
            if data_src_match:
                poster = data_src_match.group(1)
            elif img_match:
                poster = img_match.group(1)

            title_match = re.search(r'<img[^>]+alt="([^"]+)"', item)
            name = slug.replace("-", " ").title()
            if title_match:
                name = title_match.group(1)

            metas.append({
                "id": f"stmify:{slug}",
                "type": "series",
                "name": name,
                "poster": poster,
                "description": f"Watch {name} live on Stmify."
            })

        return metas
    except Exception as e:
        print(f"Error scraping page {page}: {e}")
        return []

def resolve_stream_info(slug):
    channel_url = f"{STMIFY_BASE_URL}/live-tv/{slug}/"
    try:
        r = requests.get(channel_url, headers=COMMON_HEADERS, timeout=10)
        if r.status_code != 200:
            return None

        iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', r.text)
        if not iframe_match:
            iframe_match = re.search(r'src="(https://cdn\.stmify\.com/embed[^"]+)"', r.text)

        if not iframe_match:
            return None

        iframe_src = iframe_match.group(1)
        if iframe_src.startswith("//"):
            iframe_src = "https:" + iframe_src

        headers = COMMON_HEADERS.copy()
        headers["Referer"] = channel_url

        r_embed = requests.get(iframe_src, headers=headers, timeout=10)
        if r_embed.status_code != 200:
            return None

        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', r_embed.text)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', r_embed.text)

        if not stream_id_match or not country_match:
            return None

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)

        api_url = f"{CDN_BASE_URL}/embed-free/fetch_streams.php?country={country}"
        api_headers = COMMON_HEADERS.copy()
        api_headers["Referer"] = iframe_src
        api_headers["X-Requested-With"] = "XMLHttpRequest"

        r_api = requests.get(api_url, headers=api_headers, timeout=10)
        if r_api.status_code != 200:
            return None

        data = r_api.json()
        if stream_key in data:
            return data[stream_key]

    except Exception as e:
        print(f"Error resolving {slug}: {e}")
    return None

def get_stmify_stream(stmify_id):
    """Resolves a Stmify ID (stmify:slug) to a stream URL dynamically."""
    if not stmify_id.startswith("stmify:"):
        return []

    slug = stmify_id.split(":")[1]
    info = resolve_stream_info(slug)

    if not info:
        return []

    stream_url = info.get("url")
    if not stream_url:
        return []

    # User Request: "CSAK M3U8 LINKEK VANNAK, CSAK AZOKAT KÉREM... SEMMI DRM-ES LINK"
    # We strictly filter for .m3u8.

    if ".m3u8" not in stream_url.lower():
        # It's not HLS (likely DASH .mpd). User wants to skip these.
        return []

    # Headers for playback
    headers = {
        "User-Agent": COMMON_HEADERS["User-Agent"],
        "Referer": "https://stmify.com/",
        "Origin": "https://stmify.com"
    }

    stream_obj = {
        "name": "Stmify",
        "title": f"Live: {slug.replace('-', ' ').title()}",
        "url": stream_url,
        "behaviorHints": {
            "notWebReady": True,
            "proxyHeaders": {
                "request": headers
            }
        }
    }
    return [stream_obj]
