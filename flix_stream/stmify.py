import json
import logging
import os
from functools import lru_cache


logger = logging.getLogger(__name__)

STMIFY_BASE_URL = "https://stmify.com"
JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "stmify_channels.json",
)

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": f"{STMIFY_BASE_URL}/",
    "Origin": STMIFY_BASE_URL,
}


def _normalize_int(value, default):
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed


def _load_channels_data():
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load Stmify static catalog: %s", exc)
        return []
    return payload if isinstance(payload, list) else []


@lru_cache(maxsize=1)
def load_channels():
    return _load_channels_data()


def get_stmify_catalog(skip=0, limit=20):
    skip = max(_normalize_int(skip, 0), 0)
    limit = max(_normalize_int(limit, 20), 1)
    channels = list(load_channels())
    channels.sort(key=lambda item: 0 if isinstance(item, dict) and item.get("stream_url") else 1)

    metas = []
    for channel in channels[skip : skip + limit]:
        if not isinstance(channel, dict):
            continue
        channel_id = str(channel.get("id") or "").strip()
        if not channel_id:
            slug = str(channel.get("slug") or "").strip()
            if not slug:
                continue
            channel_id = f"stmify:{slug}"
        name = str(channel.get("name") or "").strip() or channel_id
        description = str(channel.get("description") or "").strip()
        if not description:
            description = f"Watch {name} live on Stmify."
        if channel.get("stream_url"):
            description = f"{description}\n(Stream Available)"
        else:
            description = f"{description}\n(No Stream)"
        metas.append(
            {
                "id": channel_id,
                "type": "series",
                "name": name,
                "poster": channel.get("poster"),
                "description": description,
            }
        )
    return metas


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
    canonical_id, slug = _normalize_stmify_id(stmify_id)
    if not canonical_id:
        return None, None

    channels = load_channels()
    channel = next(
        (
            item
            for item in channels
            if isinstance(item, dict) and (item.get("slug") == slug or item.get("id") == canonical_id)
        ),
        None,
    )
    if not isinstance(channel, dict):
        return None, None
    return canonical_id, channel


def get_stmify_stream(stmify_id):
    canonical_id, channel = get_stmify_channel(stmify_id)
    if not canonical_id or not channel:
        return []

    channel_name = str(channel.get("name") or canonical_id.split(":", 1)[1].replace("-", " ").title()).strip()
    stream_url = channel.get("stream_url")
    if not stream_url:
        return []

    return [
        {
            "name": "Stmify",
            "title": f"Live: {channel_name}",
            "url": stream_url,
            "behaviorHints": {
                "notWebReady": True,
                "proxyHeaders": {
                    "request": {
                        "User-Agent": COMMON_HEADERS["User-Agent"],
                        "Referer": COMMON_HEADERS["Referer"],
                        "Origin": COMMON_HEADERS["Origin"],
                    }
                },
            },
        }
    ]


def get_stmify_meta(stmify_id):
    canonical_id, channel = get_stmify_channel(stmify_id)
    if not canonical_id or not channel:
        return None

    name = str(channel.get("name") or canonical_id).strip()
    description = str(channel.get("description") or "").strip() or f"Watch {name} live on Stmify."
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
