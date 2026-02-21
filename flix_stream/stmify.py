import base64
import binascii
import json
import logging
import os
import re
from functools import lru_cache

import requests
from flask import has_request_context, request


logger = logging.getLogger(__name__)

STMIFY_BASE_URL = "https://stmify.com"
JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "stmify_channels.json",
)
CLEARKEY_SCHEME_ID = "urn:uuid:1077efec-c0b2-4d02-ace3-3c1e52e2fb4b"
DASHIF_NAMESPACE = "https://dashif.org/guidelines/clear-key"

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


def _hex_to_uuid(value):
    token = str(value or "").strip().lower()
    if len(token) != 32:
        return None
    return (
        f"{token[0:8]}-{token[8:12]}-{token[12:16]}-"
        f"{token[16:20]}-{token[20:32]}"
    ).upper()


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

    slug = canonical_id.split(":", 1)[1]
    channel_name = str(channel.get("name") or slug.replace("-", " ").title()).strip()
    stream_url = channel.get("stream_url")
    if not stream_url:
        return []

    if _is_valid_hex_key(channel.get("k1")) and _is_valid_hex_key(channel.get("k2")):
        if has_request_context():
            base_url = request.url_root.rstrip("/")
            proxy_url = f"{base_url}/stmify/proxy/{slug}.mpd"
        else:
            proxy_url = f"/stmify/proxy/{slug}.mpd"
        return [
            {
                "name": "Stmify (DRM)",
                "title": f"Live: {channel_name}",
                "url": proxy_url,
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


def _inject_dashif_namespace(mpd_content):
    if "xmlns:dashif=" in mpd_content:
        return mpd_content
    if "<MPD " in mpd_content:
        return mpd_content.replace("<MPD ", f'<MPD xmlns:dashif="{DASHIF_NAMESPACE}" ', 1)
    if "<MPD>" in mpd_content:
        return mpd_content.replace("<MPD>", f'<MPD xmlns:dashif="{DASHIF_NAMESPACE}">', 1)
    return mpd_content


def _inject_base_url(mpd_content, base_url):
    if "<BaseURL>" in mpd_content:
        return mpd_content
    patched, count = re.subn(
        r"(<Period\b[^>]*>)",
        lambda match: f"{match.group(1)}<BaseURL>{base_url}</BaseURL>",
        mpd_content,
        count=1,
    )
    if count:
        return patched
    return mpd_content


def _strip_non_clearkey_drm_blocks(mpd_content):
    patterns = [
        r'<ContentProtection[^>]*schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"[^>]*>.*?</ContentProtection>',
        r'<ContentProtection[^>]*schemeIdUri="urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95"[^>]*>.*?</ContentProtection>',
    ]
    patched = mpd_content
    for pattern in patterns:
        patched = re.sub(pattern, "", patched, flags=re.DOTALL | re.IGNORECASE)
    return patched


def _inject_clearkey_content_protection(mpd_content, license_url, default_kid=None):
    # Remove stale ClearKey blocks before reinject to avoid duplicates.
    mpd_content = re.sub(
        r'<ContentProtection[^>]*schemeIdUri="' + re.escape(CLEARKEY_SCHEME_ID) + r'"[^>]*>.*?</ContentProtection>',
        "",
        mpd_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    mpd_content = _strip_non_clearkey_drm_blocks(mpd_content)

    kid_attr = ""
    if default_kid:
        kid_attr = f' xmlns:cenc="urn:mpeg:cenc:2013" cenc:default_KID="{default_kid}"'
    protection_xml = (
        f'<ContentProtection schemeIdUri="{CLEARKEY_SCHEME_ID}" value="ClearKey"{kid_attr}>'
        f"<dashif:Laurl>{license_url}</dashif:Laurl>"
        "</ContentProtection>"
    )
    patched, _ = re.subn(
        r"(<AdaptationSet\b[^>]*>)",
        lambda match: f"{match.group(1)}{protection_xml}",
        mpd_content,
        count=0,
    )
    return patched


def get_stmify_proxy_mpd(slug, license_url):
    _, channel = get_stmify_channel(f"stmify:{slug}")
    if not isinstance(channel, dict):
        return "Channel not found", 404

    stream_url = str(channel.get("stream_url") or "").strip()
    if not stream_url:
        return "Channel stream not found", 404

    try:
        response = requests.get(stream_url, headers=COMMON_HEADERS, timeout=12)
    except Exception as exc:
        logger.warning("Stmify proxy request failed for %s: %s", slug, exc)
        return "Proxy error", 500
    if response.status_code != 200:
        return f"Upstream error: {response.status_code}", 502

    mpd_content = str(response.text or "")
    default_kid = _hex_to_uuid(channel.get("k1")) if _is_valid_hex_key(channel.get("k1")) else None
    base_url = stream_url.rsplit("/", 1)[0] + "/"
    mpd_content = _inject_dashif_namespace(mpd_content)
    mpd_content = _inject_base_url(mpd_content, base_url)
    mpd_content = _inject_clearkey_content_protection(mpd_content, license_url, default_kid=default_kid)
    return mpd_content, 200


def get_stmify_license_payload(slug):
    _, channel = get_stmify_channel(f"stmify:{slug}")
    if not isinstance(channel, dict):
        return None

    k1 = channel.get("k1")
    k2 = channel.get("k2")
    if not (_is_valid_hex_key(k1) and _is_valid_hex_key(k2)):
        return None

    return {
        "keys": [
            {
                "kty": "oct",
                "kid": _hex_to_b64url(k1),
                "k": _hex_to_b64url(k2),
            }
        ],
        "type": "temporary",
    }


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
