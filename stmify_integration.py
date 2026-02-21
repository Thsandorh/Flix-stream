import json
import os
import requests
import base64
import binascii
import re  # Added re import
from flask import Blueprint, jsonify, request, Response, stream_with_context
from functools import lru_cache

stmify_bp = Blueprint('stmify', __name__)

STMIFY_BASE_URL = "https://stmify.com"
CDN_BASE_URL = "https://cdn.stmify.com"
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'stmify_channels.json')

# Common headers to mimic a browser
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": STMIFY_BASE_URL + "/",
    "Origin": STMIFY_BASE_URL
}

def load_channels():
    try:
        with open(JSON_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading Stmify channels: {e}")
        return []

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

    metas = get_stmify_catalog_static(skip)
    return jsonify({"metas": metas})

@stmify_bp.route('/catalog/series/stmify-live/skip=<int:skip>.json')
def stmify_catalog_pagination(skip):
    metas = get_stmify_catalog_static(skip)
    return jsonify({"metas": metas})

def get_stmify_catalog_static(skip=0, limit=20):
    channels = load_channels()
    # Sort: channels with 'stream_url' come first
    channels.sort(key=lambda x: 0 if x.get('stream_url') else 1)

    subset = channels[skip : skip + limit]
    metas = []
    for c in subset:
        metas.append({
            "id": c["id"],
            "type": "series",
            "name": c["name"],
            "poster": c["poster"],
            "description": c.get("description", "") + ("\n(Stream Available)" if c.get("stream_url") else "\n(No Stream)")
        })
    return metas

def get_stmify_stream(stmify_id):
    if not stmify_id.startswith("stmify:"):
        return []

    slug = stmify_id.split(":")[1]
    channels = load_channels()

    channel = next((c for c in channels if c["slug"] == slug), None)

    if channel and channel.get("stream_url"):
        stream_url = channel["stream_url"]

        # Check for DRM keys
        k1 = channel.get("k1")
        k2 = channel.get("k2")

        if k1 and k2:
            # Use local proxy to inject DRM signaling
            base_url = request.url_root.rstrip('/')
            proxy_url = f"{base_url}/stmify/proxy/{slug}.mpd"

            return [{
                "name": "Stmify (DRM)",
                "title": f"Live: {channel['name']}",
                "url": proxy_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": COMMON_HEADERS["User-Agent"],
                            "Referer": "https://stmify.com/",
                            "Origin": "https://stmify.com"
                        }
                    }
                }
            }]

        # Standard Stream
        headers = {
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Referer": "https://stmify.com/",
            "Origin": "https://stmify.com"
        }

        stream_obj = {
            "name": "Stmify",
            "title": f"Live: {channel['name']}",
            "url": stream_url,
            "behaviorHints": {
                "notWebReady": True,
                "proxyHeaders": {
                    "request": headers
                }
            }
        }
        return [stream_obj]

    return []

@stmify_bp.route('/stmify/proxy/<slug>.mpd')
def proxy_mpd(slug):
    """Fetches original MPD, injects ClearKey protection and BaseURL, and serves it."""
    channels = load_channels()
    channel = next((c for c in channels if c["slug"] == slug), None)

    if not channel or not channel.get("stream_url"):
        return "Channel not found", 404

    original_url = channel["stream_url"]

    try:
        r = requests.get(original_url, headers=COMMON_HEADERS, timeout=10)
        if r.status_code != 200:
            return f"Upstream error: {r.status_code}", 502

        mpd_content = r.text

        # Calculate BaseURL from original URL (everything up to the last slash)
        base_url_val = original_url.rsplit('/', 1)[0] + '/'

        # Construct License URL
        # Stremio will call this.
        license_url = f"{request.url_root.rstrip('/')}/stmify/license/{slug}"

        # Injection XML
        # 1. BaseURL
        base_url_xml = f"<BaseURL>{base_url_val}</BaseURL>"

        # 2. ClearKey ContentProtection
        # We assume the player supports DASH-IF guidelines or generic ClearKey
        clearkey_xml = f"""
        <ContentProtection schemeIdUri="urn:uuid:1077efec-c0b2-4d02-ace3-3c1e52e2fb4b" value="ClearKey">
            <dashif:Laurl>{license_url}</dashif:Laurl>
        </ContentProtection>
        """

        # 3. Add Namespace if missing (simple check)
        if "xmlns:dashif" not in mpd_content:
            mpd_content = mpd_content.replace('<MPD ', '<MPD xmlns:dashif="https://dashif.org/guidelines/clear-key" ')

        # Inject BaseURL after <Period ...> or inside <MPD>
        # Simple regex replacement
        if "<Period" in mpd_content:
            mpd_content = mpd_content.replace('>', f'>{base_url_xml}', 1) # Inject after first tag closure? No, risky.
            # Better: Inject after <Period ...> start tag closure.
            mpd_content = re.sub(r'(<Period[^>]*>)', fr'\1{base_url_xml}', mpd_content, count=1)
        else:
            # Inject at start of MPD content?
            pass

        # Inject ContentProtection
        # Look for existing ContentProtection and append ours
        # Or inject into AdaptationSet
        if "<AdaptationSet" in mpd_content:
            mpd_content = re.sub(r'(<AdaptationSet[^>]*>)', fr'\1{clearkey_xml}', mpd_content, count=1)

        return Response(mpd_content, mimetype="application/dash+xml")

    except Exception as e:
        return f"Proxy error: {e}", 500

@stmify_bp.route('/stmify/license/<slug>', methods=['GET', 'POST'])
def license_server(slug):
    """Returns ClearKey license keys."""
    channels = load_channels()
    channel = next((c for c in channels if c["slug"] == slug), None)

    if not channel or not channel.get("k1") or not channel.get("k2"):
        return "Key not found", 404

    k1_hex = channel["k1"]
    k2_hex = channel["k2"]

    # Convert Hex to Base64URL (no padding)
    def hex_to_b64url(h):
        return base64.urlsafe_b64encode(binascii.unhexlify(h)).decode('utf-8').rstrip('=')

    kid = hex_to_b64url(k1_hex)
    k = hex_to_b64url(k2_hex)

    # JWK Set Format
    keys = {
        "keys": [{
            "kty": "oct",
            "k": k,
            "kid": kid
        }],
        "type": "temporary"
    }

    return jsonify(keys)
