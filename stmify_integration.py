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
    """
    Returns the Stmify Live TV catalog.
    Stremio passes 'skip' for pagination (e.g. 0, 20, 40...).
    Stmify uses page numbers (1, 2, 3...).
    Assume 20 items per page based on typical WordPress pagination.
    """
    try:
        skip = request.args.get("skip")
        if skip:
            skip = int(skip)
        else:
            # Stremio might pass it in the path for some addons,
            # but usually query param or part of the extra args.
            # If standard Stremio addon pattern /catalog/type/id/skip=X.json is used,
            # Flask routing would need to capture it.
            # However, standard Stremio protocol for catalogs often uses
            # /catalog/{type}/{id}.json and extra params are handled differently
            # or it uses resource args.
            # For simplicity, we'll check query params or extra path if needed.
            # But let's look at how we registered it: /catalog/series/stmify-live.json
            # Stremio might append /skip=20.json.
            # We'll use a simpler approach: fetch page 1 by default.
            skip = 0

        # Try to parse skip from request path if it's there (e.g. .../skip=20.json)
        # But Flask route is fixed. We'll rely on query string if provided,
        # or just fetch the first page.
        # To support proper pagination, we'd need a route like:
        # /catalog/series/stmify-live/skip=<skip>.json
        pass
    except:
        skip = 0

    page = (skip // 20) + 1
    metas = get_stmify_catalog(page)
    return jsonify({"metas": metas})

@stmify_bp.route('/catalog/series/stmify-live/skip=<int:skip>.json')
def stmify_catalog_pagination(skip):
    page = (skip // 20) + 1
    metas = get_stmify_catalog(page)
    return jsonify({"metas": metas})

@lru_cache(maxsize=32)
def get_stmify_catalog(page=1):
    """Scrapes the Stmify Live TV channel list."""
    url = f"{STMIFY_BASE_URL}/live-tv/"
    if page > 1:
        url = f"{STMIFY_BASE_URL}/live-tv/page/{page}/"

    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        html = r.text

        metas = []
        # Regex to find archive items
        # Structure: <div class="archive-item"> ... <a href="..."> ... <img ... alt="..."> ... </a>
        # We can use a relatively robust regex or just split by archive-item

        # Pattern for the link and image
        # <a href="https://stmify.com/live-tv/tv1/">
        # <img ... src="..." ... alt="TV1" ... />

        # Let's find all <div class="archive-item"> blocks first
        items = html.split('class="archive-item"')
        for item in items[1:]: # Skip preamble
            # Extract link
            link_match = re.search(r'<a\s+href="([^"]+)"', item)
            if not link_match:
                continue
            link = link_match.group(1)

            # Extract slug from link
            # https://stmify.com/live-tv/tv1/ -> tv1
            slug_match = re.search(r'/live-tv/([^/]+)/', link)
            if not slug_match:
                continue
            slug = slug_match.group(1)

            # Extract image
            img_match = re.search(r'<img[^>]+src="([^"]+)"', item)
            # Sometimes src is base64 placeholder and data-src is real
            data_src_match = re.search(r'<img[^>]+data-src="([^"]+)"', item)

            poster = None
            if data_src_match:
                poster = data_src_match.group(1)
            elif img_match:
                poster = img_match.group(1)

            # Extract title
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
        print(f"Error fetching catalog page {page}: {e}")
        return []

def get_stmify_stream(stmify_id):
    """Resolves a Stmify ID (stmify:slug) to a stream URL."""
    if not stmify_id.startswith("stmify:"):
        return []

    slug = stmify_id.split(":")[1]
    channel_url = f"{STMIFY_BASE_URL}/live-tv/{slug}/"

    try:
        # Step 1: Get Channel Page
        r = requests.get(channel_url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()

        # Step 2: Find Iframe Source
        # <iframe src="//cdn.stmify.com/embed-free/v1/tv1-lt-jw" ...
        iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', r.text)
        if not iframe_match:
            # Try alternate pattern
            iframe_match = re.search(r'src="(https://cdn\.stmify\.com/embed[^"]+)"', r.text)

        if not iframe_match:
            return []

        iframe_src = iframe_match.group(1)
        if iframe_src.startswith("//"):
            iframe_src = "https:" + iframe_src

        # Step 3: Fetch Embed Page
        # We need to set Referer to the channel page
        headers = COMMON_HEADERS.copy()
        headers["Referer"] = channel_url

        r_embed = requests.get(iframe_src, headers=headers, timeout=10)
        r_embed.raise_for_status()
        embed_html = r_embed.text

        # Step 4: Extract streamId and country
        # const streamId = "TV1";
        # const country = "lt";
        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', embed_html)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', embed_html)

        if not stream_id_match or not country_match:
            return []

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)

        # Step 5: Call API
        api_url = f"{CDN_BASE_URL}/embed-free/fetch_streams.php?country={country}"
        # Important: X-Requested-With header
        api_headers = COMMON_HEADERS.copy()
        api_headers["Referer"] = iframe_src # "https://cdn.stmify.com/..."
        api_headers["X-Requested-With"] = "XMLHttpRequest"

        r_api = requests.get(api_url, headers=api_headers, timeout=10)
        r_api.raise_for_status()
        data = r_api.json()

        # Step 6: Extract Stream URL
        if stream_key in data:
            stream_info = data[stream_key]
            stream_url = stream_info.get("url")

            if not stream_url:
                return []

            # Check for DRM
            k1 = stream_info.get("k1")
            k2 = stream_info.get("k2")

            # Construct stream object
            stream_obj = {
                "name": "Stmify",
                "title": f"Live: {slug.replace('-', ' ').title()}",
                "url": stream_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": COMMON_HEADERS["User-Agent"],
                            "Referer": CDN_BASE_URL + "/"
                        }
                    }
                }
            }

            # If ClearKey is present, we might need to handle it.
            # Currently standard Stremio players might not support direct k1/k2 JSON injection
            # without a specific format or proxy.
            # But we will return the URL. If it's DASH+ClearKey, generic players might fail
            # unless we provide license info.
            # However, for now we return what we have.

            return [stream_obj]

        return []

    except Exception as e:
        print(f"Error resolving Stmify stream {slug}: {e}")
        return []
