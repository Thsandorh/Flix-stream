import logging
import re
from functools import lru_cache

import requests


logger = logging.getLogger(__name__)

STMIFY_BASE_URL = "https://stmify.com"
CDN_BASE_URL = "https://cdn.stmify.com"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": f"{STMIFY_BASE_URL}/",
    "Origin": STMIFY_BASE_URL,
}


def _normalize_page(page):
    try:
        parsed = int(page)
    except Exception:
        return 1
    return max(parsed, 1)


@lru_cache(maxsize=32)
def get_stmify_catalog(page=1):
    page = _normalize_page(page)
    url = f"{STMIFY_BASE_URL}/live-tv/"
    if page > 1:
        url = f"{STMIFY_BASE_URL}/live-tv/page/{page}/"

    try:
        response = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch Stmify catalog page %s: %s", page, exc)
        return []

    html = response.text
    items = html.split('class="archive-item"')
    metas = []
    for item in items[1:]:
        link_match = re.search(r'<a\s+href="([^"]+)"', item)
        if not link_match:
            continue

        slug_match = re.search(r"/live-tv/([^/]+)/", link_match.group(1))
        if not slug_match:
            continue
        slug = slug_match.group(1)

        data_src_match = re.search(r'<img[^>]+data-src="([^"]+)"', item)
        img_match = re.search(r'<img[^>]+src="([^"]+)"', item)
        title_match = re.search(r'<img[^>]+alt="([^"]+)"', item)

        poster = data_src_match.group(1) if data_src_match else (img_match.group(1) if img_match else None)
        name = title_match.group(1) if title_match else slug.replace("-", " ").title()
        metas.append(
            {
                "id": f"stmify:{slug}",
                "type": "series",
                "name": name,
                "poster": poster,
                "description": f"Watch {name} live on Stmify.",
            }
        )

    return metas


def _extract_iframe_src(html):
    iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', html)
    if not iframe_match:
        iframe_match = re.search(r'src="(https://cdn\.stmify\.com/embed[^"]+)"', html)
    if not iframe_match:
        return None
    iframe_src = iframe_match.group(1)
    if iframe_src.startswith("//"):
        return f"https:{iframe_src}"
    return iframe_src


def get_stmify_stream(stmify_id):
    if not str(stmify_id).startswith("stmify:"):
        return []

    slug = str(stmify_id).split(":", 1)[1].strip()
    if not slug:
        return []
    channel_url = f"{STMIFY_BASE_URL}/live-tv/{slug}/"

    try:
        response = requests.get(channel_url, headers=COMMON_HEADERS, timeout=10)
        response.raise_for_status()
        iframe_src = _extract_iframe_src(response.text)
        if not iframe_src:
            return []

        iframe_headers = dict(COMMON_HEADERS)
        iframe_headers["Referer"] = channel_url
        iframe_response = requests.get(iframe_src, headers=iframe_headers, timeout=10)
        iframe_response.raise_for_status()
        embed_html = iframe_response.text

        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', embed_html)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', embed_html)
        if not stream_id_match or not country_match:
            return []

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)

        api_url = f"{CDN_BASE_URL}/embed-free/fetch_streams.php?country={country}"
        api_headers = dict(COMMON_HEADERS)
        api_headers["Referer"] = iframe_src
        api_headers["X-Requested-With"] = "XMLHttpRequest"
        api_response = requests.get(api_url, headers=api_headers, timeout=10)
        api_response.raise_for_status()
        data = api_response.json()
        if not isinstance(data, dict):
            return []

        stream_info = data.get(stream_key)
        if not isinstance(stream_info, dict):
            return []

        stream_url = stream_info.get("url")
        if not stream_url:
            return []

        return [
            {
                "name": "Stmify",
                "title": f"Live: {slug.replace('-', ' ').title()}",
                "url": stream_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": COMMON_HEADERS["User-Agent"],
                            "Referer": f"{CDN_BASE_URL}/",
                        }
                    },
                },
            }
        ]
    except Exception as exc:
        logger.warning("Failed to resolve Stmify stream for %s: %s", slug, exc)
        return []
