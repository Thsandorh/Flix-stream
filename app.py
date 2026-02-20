import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request

from flix_stream.anime import (
    decode_b64_loose as _decode_b64_loose,
    extract_aniways_proxy_hls_details as _extract_aniways_proxy_hls_details,
    fetch_aniways_search_page as _fetch_aniways_search_page,
    fetch_aniways_streams,
    get_kitsu_anime_context,
    is_aniways_api_proxy_url as _is_aniways_api_proxy_url,
    is_likely_aniways_stream_url as _is_likely_aniways_stream_url,
    normalize_title_for_match as _normalize_title_for_match,
    resolve_aniways_id_from_kitsu,
)
from flix_stream.config import (
    ANIWAYS_API_BASE,
    ANIWAYS_COMMON_HEADERS,
    AUTOEMBED_COMMON_HEADERS,
    AUTOEMBED_SERVERS,
    COMMON_HEADERS,
    KITSU_API_BASE,
    LANG_MAP,
    MANIFEST,
    MASTER_KEY,
    SERVERS,
    TMDB_TOKEN,
    VIXSRC_BASE_URL,
    VIXSRC_COMMON_HEADERS,
)
from flix_stream.crypto import (
    _KEY_CACHE,
    decrypt_autoembed_response,
    decrypt_link,
    get_decryption_key,
)
from flix_stream.ids import (
    decode_stream_id as _decode_stream_id,
    normalize_episode_part as _normalize_episode_part,
    provider_rank,
)
from flix_stream.providers import (
    extract_braced_js_object as _extract_braced_js_object,
    extract_vixsrc_playlist_url as _extract_vixsrc_playlist_url,
    fetch_autoembed_server_streams,
    fetch_server_streams,
    fetch_vixsrc_streams,
    needs_stremio_proxy as _needs_stremio_proxy,
)
from flix_stream.subtitles import parse_subtitles
from flix_stream.tmdb import (
    get_series_context_from_imdb,
    get_tmdb_id,
    get_tmdb_id_from_cinemeta,
)


app = Flask(__name__)


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "*")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response


def parse_stream_id(content_type, raw_id):
    """Parse Stremio content ids into a provider id + optional season/episode."""
    decoded_id = _decode_stream_id(raw_id)
    parts = [p for p in decoded_id.split(":") if p]
    kind = (content_type or "").lower()

    if not parts:
        return None, None, None

    if parts[0].lower() == "tmdb":
        if len(parts) < 2:
            return None, None, None
        try:
            content_id = int(parts[1])
        except Exception:
            return None, None, None
        season = _normalize_episode_part(parts[2] if len(parts) > 2 else None)
        episode = _normalize_episode_part(parts[3] if len(parts) > 3 else None)
        return content_id, season, episode

    imdb_id = parts[0]
    season = _normalize_episode_part(parts[1] if len(parts) > 1 else None)
    episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)
    if not imdb_id.startswith("tt"):
        return None, season, episode

    content_id = get_tmdb_id(imdb_id, kind)
    return content_id, season, episode


@app.route("/")
@app.route("/configure")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    manifest_data = dict(MANIFEST)
    logo = manifest_data.get("logo")
    if isinstance(logo, str) and logo.startswith("/"):
        base = request.url_root.rstrip("/")
        manifest_data["logo"] = f"{base}{logo}"
    return jsonify(manifest_data)


@app.route("/stream/<type>/<path:id>.json")
def stream(type, id):
    # Stremio format: tt1234567[:season:episode] (may be URL-encoded).
    decoded_id = _decode_stream_id(id)
    parts = [p for p in decoded_id.split(":") if p]
    imdb_id = parts[0] if parts else ""
    kind = (type or "").lower()
    season = _normalize_episode_part(parts[1] if len(parts) > 1 else None)
    episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)

    if imdb_id.lower() in ("aniways", "kitsu"):
        source_prefix = imdb_id.lower()
        source_id = parts[1] if len(parts) > 1 else None
        if len(parts) > 3:
            aniways_episode = _normalize_episode_part(parts[3])
        else:
            aniways_episode = _normalize_episode_part(parts[2] if len(parts) > 2 else None)

        if not source_id or not aniways_episode:
            return jsonify({"streams": []})

        anime_id = source_id
        if source_prefix == "kitsu":
            anime_id = resolve_aniways_id_from_kitsu(source_id)

        if not anime_id:
            return jsonify({"streams": []})

        aniways_streams = fetch_aniways_streams(anime_id, aniways_episode)
        aniways_streams.sort(key=lambda s: (str(s.get("name", "")), str(s.get("title", ""))))
        aniways_streams.append(
            {
                "name": "Flix-Streams",
                "title": "Support development on Ko-fi",
                "externalUrl": "https://ko-fi.com/sandortoth",
            }
        )
        return jsonify({"streams": aniways_streams})

    if not imdb_id.startswith("tt"):
        return jsonify({"streams": []})

    tmdb_id = get_tmdb_id(imdb_id, kind)
    if not tmdb_id:
        return jsonify({"streams": []})

    if kind in ("series", "tv") and (not season or not episode):
        _, hint_season, hint_episode = get_series_context_from_imdb(imdb_id)
        if not season and hint_season is not None:
            season = str(hint_season)
        if not episode and hint_episode is not None:
            episode = str(hint_episode)

    if kind in ("series", "tv") and (not season or not episode):
        return jsonify({"streams": []})

    all_streams = []
    decryption_key = get_decryption_key()
    if decryption_key:
        # VidZee provider.
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(
                lambda s: fetch_server_streams(tmdb_id, s, season, episode, decryption_key),
                SERVERS,
            )
            for res in results:
                all_streams.extend(res)
    else:
        app.logger.warning("VidZee decryption key unavailable; skipping VidZee provider")

    # AutoEmbed provider.
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(
            lambda s: fetch_autoembed_server_streams(tmdb_id, s, season, episode),
            AUTOEMBED_SERVERS,
        )
        for res in results:
            all_streams.extend(res)

    # VixSrc provider.
    all_streams.extend(fetch_vixsrc_streams(tmdb_id, kind, season, episode))

    # Keep provider groups stable in the list.
    all_streams.sort(key=lambda s: (provider_rank(s), str(s.get("name", "")), str(s.get("title", ""))))

    # Keep a clickable support link as the final item in the stream list.
    all_streams.append(
        {
            "name": "Flix-Streams",
            "title": "Support development on Ko-fi",
            "externalUrl": "https://ko-fi.com/sandortoth",
        }
    )

    return jsonify({"streams": all_streams})


if __name__ == "__main__":
    # Use environment variable for port, default to 7000.
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
