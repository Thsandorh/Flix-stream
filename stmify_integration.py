import json
import os
from flask import Blueprint, jsonify, request
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
    """
    Returns the Stmify Live TV catalog from static JSON.
    """
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
    # Filter only channels that have a stream_url?
    # The user wanted "all channels", but if they don't play, it's annoying.
    # However, showing them allows the user to see what exists.
    # Let's show all, or maybe prioritize ones with streams.
    # Sorting: Valid streams first.

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
    """Resolves a Stmify ID (stmify:slug) to a stream URL from static JSON."""
    if not stmify_id.startswith("stmify:"):
        return []

    slug = stmify_id.split(":")[1]
    channels = load_channels()

    channel = next((c for c in channels if c["slug"] == slug), None)

    if channel and channel.get("stream_url"):
        stream_url = channel["stream_url"]

        # Determine headers based on URL (optional, but safe default)
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
