import base64
import binascii
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import quote, urljoin, urlparse

import requests
from flask import has_request_context, request


logger = logging.getLogger(__name__)

STMIFY_BASE_URL = "https://stmify.com"
CDN_BASE_URL = "https://cdn.stmify.com"
LIVE_RESOLVE_TTL_SECONDS = 300

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": f"{STMIFY_BASE_URL}/",
    "Origin": STMIFY_BASE_URL,
}
_LIVE_STREAM_CACHE = {}


def _is_mpd_stream_url(stream_url):
    token = str(stream_url or "").strip().lower()
    if not token:
        return False
    return bool(re.search(r"\.(mpd|dash)(?:$|[?#])", token))


def _is_m3u8_stream_url(stream_url):
    token = str(stream_url or "").strip().lower()
    if not token:
        return False
    return bool(re.search(r"\.m3u8(?:$|[?#])", token))


def _needs_stmify_hls_proxy(stream_url):
    try:
        host = (urlparse(str(stream_url or "")).hostname or "").lower()
    except Exception:
        return False
    return host == "cdn.stmify.com" or "stmify" in host


def _is_valid_hex_key(value):
    token = str(value or "").strip().lower()
    if not token:
        return False
    if len(token) != 32:
        return False
    return bool(re.fullmatch(r"[0-9a-f]+", token))


def _hex_to_b64url(value):
    raw = binascii.unhexlify(str(value).strip())
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def load_channels():
    # Deprecated: Static loading removed.
    return []


def scrape_stmify_category(path, page=1):
    base_url = f"{STMIFY_BASE_URL}/{path}/"
    if page > 1:
        base_url = f"{base_url}page/{page}/"

    try:
        resp = requests.get(base_url, headers=COMMON_HEADERS, timeout=10)
    except Exception as exc:
        logger.error("Stmify scrape failed for %s: %s", path, exc)
        return []

    if resp.status_code != 200:
        return []

    html = str(resp.text or "")
    seen_slugs = set()
    results = []

    # Regex to capture <a href=".../live-tv/slug/">...</a> content
    # We look for links pointing to /live-tv/{slug}
    pattern = re.compile(
        r'<a\s+[^>]*href=["\'](?:https?://stmify\.com)?/live-tv/([^/"\']+)/?["\'][^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(html):
        slug = match.group(1).strip()
        if not slug or slug in seen_slugs:
            continue

        content = match.group(2)

        # Attempt to find poster image
        img_match = re.search(r'(?:data-src|data-lazy-src|src)=["\']([^"\']+)["\']', content)
        poster = img_match.group(1) if img_match else None

        if poster and poster.startswith("data:"):
             better_match = re.search(r'(?:data-src|data-lazy-src)=["\']([^"\']+)["\']', content)
             if better_match:
                 poster = better_match.group(1)

        # Attempt to find title text (strip tags)
        text = re.sub(r'<[^>]+>', '', content).strip()

        if not text:
            if img_match:
                 alt_match = re.search(r'alt=["\']([^"\']+)["\']', content)
                 if alt_match:
                     text = alt_match.group(1).strip()

        if not text:
            text = slug.replace("-", " ").title()

        seen_slugs.add(slug)
        results.append({
            "id": f"stmify:{slug}",
            "type": "series",
            "name": text,
            "poster": poster,
            "description": f"Watch {text} on Stmify",
        })

    return results


def _check_catalog_item(item):
    """
    Helper to check if a catalog item has a valid, non-DRM stream.
    Returns the item if valid, None otherwise.
    Strictly checks for M3U8.
    """
    slug = item.get("id", "").replace("stmify:", "")
    if not slug:
        return None

    # Resolve the stream info
    # This caches the result so the subsequent get_stream call is fast.
    info = _get_live_stream_info(slug)
    if not info:
        # Stream not found or extraction failed
        return None

    stream_url = info.get("url")
    if not stream_url:
        return None

    if _is_mpd_stream_url(stream_url):
        # DRM protected (MPD), filter out per user request
        return None

    if not _is_m3u8_stream_url(stream_url):
        # Not M3U8 -> Probably unknown or direct file, skip to be safe
        return None

    # Optional: Verify it's actually alive with a HEAD request
    try:
        head_headers = dict(COMMON_HEADERS)
        if "cdn.stmify.com" in stream_url:
            head_headers["Referer"] = "https://cdn.stmify.com/"
            head_headers["Origin"] = "https://cdn.stmify.com"

        r = requests.head(stream_url, headers=head_headers, timeout=5)
        if r.status_code >= 400:
            return None
    except Exception:
        return None

    # Valid working M3U8 stream found
    return item


def get_stmify_catalog(catalog_id, skip=0):
    # Map catalog IDs to URL paths
    CATALOG_MAP = {
        "stmify-trending": "trending",
        "stmify-movies": "tv-genre/movies",
        "stmify-sports": "tv-genre/sports",
        "stmify-news": "tv-genre/news",
        "stmify-kids": "tv-genre/kids",
        "stmify-music": "tv-genre/music",
        "stmify-entertainment": "tv-genre/entertainment",
        "stmify-infotainment": "tv-genre/infotainment",
        "stmify-4k": "4k",
    }

    path = CATALOG_MAP.get(catalog_id)
    if not path:
        return []

    page = (skip // 20) + 1
    items = scrape_stmify_category(path, page=page)

    if not items:
        return []

    # Parallel validation of streams
    valid_items = []
    # Using thread pool to validate each item quickly
    with ThreadPoolExecutor(max_workers=20) as executor:
        for result in executor.map(_check_catalog_item, items):
            if result:
                # Add source indication to description for UI clarity
                result["description"] = f"Source: Stmify | {result.get('name')}"
                valid_items.append(result)

    return valid_items


def _normalize_stmify_id(stmify_id):
    raw_id = str(stmify_id or "").strip()
    if not raw_id.startswith("stmify:"):
        return None, None
    remainder = raw_id.split(":", 1)[1].strip()
    if not remainder:
        return None, None
    slug = remainder.split(":", 1)[0].strip()
    if not slug:
        return None, None
    return f"stmify:{slug}", slug


def get_stmify_channel(stmify_id):
    # This now just returns a dummy object based on slug, as we scrape dynamically.
    canonical_id, slug = _normalize_stmify_id(stmify_id)
    if not canonical_id:
        return None, None

    # Fallback/Default for dynamic slugs.
    if re.fullmatch(r"[a-z0-9-]+", slug):
        return canonical_id, {
            "id": canonical_id,
            "slug": slug,
            "type": "series",
            "name": slug.replace("-", " ").title(),
            "description": f"Watch {slug.replace('-', ' ').title()} live on Stmify.",
        }
    return None, None


def _resolve_stream_info_from_stmify(slug):
    channel_url = f"{STMIFY_BASE_URL}/live-tv/{slug}/"
    try:
        channel_response = requests.get(channel_url, headers=COMMON_HEADERS, timeout=12)
    except Exception as exc:
        logger.debug("Stmify channel page request failed for %s: %s", slug, exc)
        return None
    if channel_response.status_code != 200:
        return None

    iframe_match = re.search(
        r'src=["\']((?:https:)?//cdn\.stmify\.com/embed[^"\']+)["\']',
        str(channel_response.text or ""),
        flags=re.IGNORECASE,
    )
    if not iframe_match:
        return None

    iframe_src = iframe_match.group(1)
    if iframe_src.startswith("//"):
        iframe_src = f"https:{iframe_src}"

    embed_headers = dict(COMMON_HEADERS)
    embed_headers["Referer"] = channel_url
    try:
        embed_response = requests.get(iframe_src, headers=embed_headers, timeout=12)
    except Exception as exc:
        logger.debug("Stmify embed request failed for %s: %s", slug, exc)
        return None
    if embed_response.status_code != 200:
        return None

    embed_payload = str(embed_response.text or "")
    stream_match = re.search(r'const\s+streamId\s*=\s*["\']([^"\']+)["\']', embed_payload)
    country_match = re.search(r'const\s+country\s*=\s*["\']([^"\']+)["\']', embed_payload)
    if not stream_match or not country_match:
        return None

    stream_key = stream_match.group(1).strip()
    country = country_match.group(1).strip()
    if not stream_key or not country:
        return None

    api_url = f"{CDN_BASE_URL}/embed-free/fetch_streams.php?country={country}"
    api_headers = dict(COMMON_HEADERS)
    api_headers["Referer"] = iframe_src
    api_headers["X-Requested-With"] = "XMLHttpRequest"
    try:
        api_response = requests.get(api_url, headers=api_headers, timeout=12)
    except Exception as exc:
        logger.debug("Stmify fetch_streams request failed for %s: %s", slug, exc)
        return None
    if api_response.status_code != 200:
        return None

    try:
        api_data = api_response.json()
    except Exception:
        return None
    if not isinstance(api_data, dict):
        return None

    channel_entry = api_data.get(stream_key)
    if not isinstance(channel_entry, dict):
        return None

    stream_url = str(channel_entry.get("url") or "").strip()
    if not stream_url:
        return None

    return {
        "url": stream_url,
        "k1": str(channel_entry.get("k1") or "").strip(),
        "k2": str(channel_entry.get("k2") or "").strip(),
    }


def _get_live_stream_info(slug):
    now = time.time()
    cached = _LIVE_STREAM_CACHE.get(slug)
    if isinstance(cached, dict) and now - float(cached.get("ts") or 0) < LIVE_RESOLVE_TTL_SECONDS:
        return cached.get("data")

    resolved = _resolve_stream_info_from_stmify(slug)
    _LIVE_STREAM_CACHE[slug] = {"ts": now, "data": resolved}
    return resolved


def _build_hls_proxy_url(slug, target_url=None):
    encoded_target = quote(str(target_url or "").strip(), safe="")
    query = f"?u={encoded_target}" if encoded_target else ""
    if has_request_context():
        base_url = request.url_root.rstrip("/")
        return f"{base_url}/stmify/hls/{slug}.m3u8{query}"
    return f"/stmify/hls/{slug}.m3u8{query}"


def get_stmify_stream(stmify_id):
    canonical_id, channel = get_stmify_channel(stmify_id)
    if not canonical_id or not channel:
        return []

    slug = canonical_id.split(":", 1)[1]
    channel_name = str(channel.get("name") or slug.replace("-", " ").title()).strip()
    live_info = _get_live_stream_info(slug)
    stream_url = str((live_info or {}).get("url") or channel.get("stream_url") or "").strip()
    if not stream_url:
        return []

    # Strict filter for streams too
    if not _is_m3u8_stream_url(stream_url) or _is_mpd_stream_url(stream_url):
        return []

    if _needs_stmify_hls_proxy(stream_url):
        return [
            {
                "name": "Stmify",
                "title": f"Live: {channel_name}",
                "url": _build_hls_proxy_url(slug),
                "behaviorHints": {
                    "notWebReady": True,
                },
            }
        ]

    return [
        {
            "name": "Stmify",
            "title": f"Live: {channel_name}",
            "url": stream_url,
            "behaviorHints": {
                "notWebReady": True,
            },
        },
        {
            "name": "Stmify (HLS Proxy)",
            "title": f"Live: {channel_name}",
            "url": _build_hls_proxy_url(slug, stream_url),
            "behaviorHints": {
                "notWebReady": True,
            },
        },
    ]


def _rewrite_m3u8_for_proxy(m3u8_content, source_url, slug):
    source_url = str(source_url or "").strip()
    lines = str(m3u8_content or "").splitlines()
    rewritten = []

    for raw_line in lines:
        line = str(raw_line or "")
        stripped = line.strip()
        if not stripped:
            rewritten.append(line)
            continue

        if stripped.startswith("#"):
            if 'URI="' in line:
                line = re.sub(
                    r'URI="([^"]+)"',
                    lambda match: f'URI="{_build_hls_proxy_url(slug, urljoin(source_url, match.group(1).strip()))}"',
                    line,
                )
            rewritten.append(line)
            continue

        target = urljoin(source_url, stripped)
        rewritten.append(_build_hls_proxy_url(slug, target))

    return "\n".join(rewritten)


def get_stmify_hls_payload(slug, target_url=None):
    _, channel = get_stmify_channel(f"stmify:{slug}")
    if not isinstance(channel, dict):
        return "Channel not found", 404, "text/plain; charset=utf-8"

    live_info = _get_live_stream_info(slug)
    if target_url:
        stream_url = str(target_url).strip()
    else:
        stream_url = str((live_info or {}).get("url") or channel.get("stream_url") or "").strip()
    if not stream_url:
        return "Channel stream not found", 404, "text/plain; charset=utf-8"

    parsed_target = urlparse(stream_url)
    if parsed_target.scheme not in ("http", "https"):
        return "Invalid target URL", 400, "text/plain; charset=utf-8"
    if has_request_context():
        req_host = (request.host or "").split(":", 1)[0].lower()
        if (parsed_target.hostname or "").lower() == req_host and parsed_target.path.startswith("/stmify/hls/"):
            return "Invalid proxy target", 400, "text/plain; charset=utf-8"

    try:
        req_headers = dict(COMMON_HEADERS)
        # If accessing cdn.stmify.com, adjust headers to avoid cross-origin blocks
        if "cdn.stmify.com" in stream_url:
            req_headers["Referer"] = "https://cdn.stmify.com/"
            req_headers["Origin"] = "https://cdn.stmify.com"

        response = requests.get(stream_url, headers=req_headers, timeout=15)
    except Exception as exc:
        logger.warning("Stmify HLS proxy request failed for %s: %s", slug, exc)
        return "Proxy error", 500, "text/plain; charset=utf-8"
    if response.status_code != 200:
        return f"Upstream error: {response.status_code}", 502, "text/plain; charset=utf-8"

    upstream_type = str(response.headers.get("Content-Type") or "").lower()
    is_playlist = _is_m3u8_stream_url(stream_url) or "mpegurl" in upstream_type
    if not is_playlist:
        content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
        return response.content, 200, content_type

    rewritten = _rewrite_m3u8_for_proxy(response.text, stream_url, slug)
    return rewritten, 200, "application/vnd.apple.mpegurl; charset=utf-8"


def get_stmify_meta(stmify_id):
    canonical_id, channel = get_stmify_channel(stmify_id)
    if not canonical_id or not channel:
        return None

    name = str(channel.get("name") or canonical_id).strip()
    description = str(channel.get("description") or "").strip() or f"Watch {name} live on Stmify."

    # Add source attribution clearly
    if "Source: Stmify" not in description:
        description += "\n\nSource: Stmify"

    return {
        "id": canonical_id,
        "type": "series",
        "name": name,
        "poster": channel.get("poster"),
        "background": channel.get("poster"),
        "description": description,
        "genres": ["Live TV"],
        "videos": [
            {
                "id": canonical_id,
                "title": "Live",
                "season": 1,
                "episode": 1,
            }
        ],
    }
