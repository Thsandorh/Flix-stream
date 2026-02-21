import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request

from flix_stream.anime import (
    fetch_aniways_streams,
    get_aniways_anime_context,
    get_kitsu_anime_context,
    resolve_aniways_id_from_kitsu,
)
from flix_stream.anime_id_resolver import (
    pick_best_tmdb_candidate,
    resolve_external_ids_from_mal_anilist,
)
from flix_stream.config import AUTOEMBED_SERVERS, MANIFEST, SERVERS
from flix_stream.crypto import get_decryption_key
from flix_stream.ids import decode_stream_id, normalize_episode_part, provider_rank
from flix_stream.providers import (
    fetch_autoembed_server_streams,
    fetch_server_streams,
    fetch_vixsrc_streams,
)
from flix_stream.superembed import fetch_superembed_streams
from flix_stream.runtime_config import (
    DEFAULT_ADDON_CONFIG,
    decode_addon_config_token,
    encode_addon_config,
    normalize_addon_config,
)
from flix_stream.famelack import (
    get_famelack_catalog,
    get_famelack_countries,
    get_famelack_meta,
    get_famelack_streams,
)
from flix_stream.tmdb import get_series_context_from_imdb, get_tmdb_id, search_tmdb_id_by_title
from flix_stream.wyzie import fetch_wyzie_subtitles, merge_subtitles


app = Flask(__name__)


def _support_stream():
    return {
        "name": "Flix-Streams",
        "title": "Support development on Ko-fi",
        "externalUrl": "https://ko-fi.com/sandortoth",
    }


def _attach_subtitles(streams, subtitles):
    if not subtitles:
        return streams
    for stream_obj in streams:
        if not isinstance(stream_obj, dict) or not stream_obj.get("url"):
            continue
        stream_obj["subtitles"] = merge_subtitles(stream_obj.get("subtitles"), subtitles)
    return streams


def _resolve_tmdb_for_anime(source_prefix, source_id, anime_id):
    if source_prefix == "kitsu":
        ctx = get_kitsu_anime_context(source_id)
        title_candidates = (ctx.get("titles") or [])[:6]
        media_type = str(ctx.get("media_type") or "").lower()
        hint = "movie" if media_type == "movie" else "series"
        year = None
        mal_id = ctx.get("mal_id")
        anilist_id = ctx.get("anilist_id")
    else:
        ctx = get_aniways_anime_context(anime_id)
        title_candidates = (ctx.get("titles") or [])[:6]
        media_type = str(ctx.get("media_type") or "").lower()
        hint = "movie" if media_type == "movie" else "series"
        year = ctx.get("season_year")
        mal_id = ctx.get("mal_id")
        anilist_id = ctx.get("anilist_id")

    # Primary path: resolve by stable external ids (MAL/AniList -> Wikidata -> TMDB/IMDb).
    external_candidates = resolve_external_ids_from_mal_anilist(mal_id=mal_id, anilist_id=anilist_id)
    tmdb_id, tmdb_kind, imdb_id = pick_best_tmdb_candidate(external_candidates, hint=hint)
    if tmdb_id:
        return tmdb_id, tmdb_kind
    if imdb_id and str(imdb_id).startswith("tt"):
        kind_hint = "movie" if hint == "movie" else "series"
        resolved_tmdb = get_tmdb_id(imdb_id, kind_hint)
        if resolved_tmdb:
            return resolved_tmdb, ("movie" if kind_hint == "movie" else "tv")

    for title in title_candidates:
        tmdb_id, tmdb_kind = search_tmdb_id_by_title(title, hint, year)
        if tmdb_id:
            return tmdb_id, tmdb_kind

    # Fallback without type hint for ambiguous titles.
    for title in title_candidates[:3]:
        tmdb_id, tmdb_kind = search_tmdb_id_by_title(title, None, year)
        if tmdb_id:
            return tmdb_id, tmdb_kind

    return None, None


def _build_manifest(addon_config):
    manifest_data = dict(MANIFEST)
    resources = list(manifest_data.get("resources") or [])
    id_prefixes = list(manifest_data.get("idPrefixes") or [])
    catalogs = list(manifest_data.get("catalogs") or [])

    # Ensure resources for TV
    if "catalog" not in resources:
        resources.append("catalog")
    if "meta" not in resources:
        resources.append("meta")

    # Famelack Integration
    famelack_countries = addon_config.get("famelack_countries")
    if famelack_countries:
        if "famelack" not in id_prefixes:
            id_prefixes.append("famelack")

        all_countries = get_famelack_countries()
        for code in famelack_countries:
            code = code.lower()
            country_name = all_countries.get(code.upper(), {}).get("country", code.upper())
            catalogs.append({
                "type": "series",
                "id": f"famelack-{code}",
                "name": f"TV - {country_name}",
                "extra": [{"name": "skip", "isRequired": False}]
            })
    else:
        id_prefixes = [prefix for prefix in id_prefixes if prefix != "famelack"]
        catalogs = [c for c in catalogs if not c["id"].startswith("famelack-")]

    manifest_data["resources"] = resources
    manifest_data["idPrefixes"] = id_prefixes
    manifest_data["catalogs"] = catalogs

    logo = manifest_data.get("logo")
    if isinstance(logo, str) and logo.startswith("/"):
        base = request.url_root.rstrip("/")
        manifest_data["logo"] = f"{base}{logo}"

    provider_labels = []
    if addon_config.get("enable_vidzee"):
        provider_labels.append("VidZee")
    if addon_config.get("enable_autoembed"):
        provider_labels.append("AutoEmbed")
    if addon_config.get("enable_vixsrc"):
        provider_labels.append("VixSrc")
    if addon_config.get("enable_superembed"):
        provider_labels.append("SuperEmbed")
    if addon_config.get("enable_aniways"):
        provider_labels.append("Aniways")
    if famelack_countries:
        provider_labels.append(f"TV ({len(famelack_countries)})")

    providers_text = ", ".join(provider_labels) if provider_labels else "none"

    subtitle_state = "enabled" if addon_config.get("enable_wyzie") else "disabled"
    manifest_data["description"] = (
        f"{MANIFEST.get('description', '')} Providers: {providers_text}. Wyzie subtitles: {subtitle_state}."
    )
    return manifest_data


def _fetch_wyzie_for_regular_content(tmdb_id, kind, season, episode, addon_config):
    if not addon_config.get("enable_wyzie"):
        return []
    wyzie_season = season if kind in ("series", "tv") else None
    wyzie_episode = episode if kind in ("series", "tv") else None
    return fetch_wyzie_subtitles(tmdb_id, wyzie_season, wyzie_episode, addon_config)


def _fetch_wyzie_for_anime_ids(source_prefix, source_id, anime_id, season, episode, addon_config):
    if not addon_config.get("enable_wyzie"):
        return []
    if not addon_config.get("wyzie_apply_to_aniways_ids"):
        return []

    tmdb_id, tmdb_kind = _resolve_tmdb_for_anime(source_prefix, source_id, anime_id)
    if not tmdb_id:
        return []

    wyzie_season = None
    wyzie_episode = None
    if tmdb_kind == "tv" and episode:
        wyzie_season = season or "1"
        wyzie_episode = episode

    return fetch_wyzie_subtitles(tmdb_id, wyzie_season, wyzie_episode, addon_config)


def _fetch_provider_streams(tmdb_id, kind, season, episode, addon_config):
    all_streams = []

    def _fetch_vidzee_streams():
        decryption_key = get_decryption_key()
        if not decryption_key:
            app.logger.warning("VidZee decryption key unavailable; skipping VidZee provider")
            return []

        streams = []
        with ThreadPoolExecutor(max_workers=min(10, len(SERVERS) or 1)) as executor:
            for res in executor.map(
                lambda s: fetch_server_streams(tmdb_id, s, season, episode, decryption_key),
                SERVERS,
            ):
                streams.extend(res)
        return streams

    def _fetch_autoembed_streams():
        streams = []
        with ThreadPoolExecutor(max_workers=min(6, len(AUTOEMBED_SERVERS) or 1)) as executor:
            for res in executor.map(
                lambda s: fetch_autoembed_server_streams(tmdb_id, s, season, episode),
                AUTOEMBED_SERVERS,
            ):
                streams.extend(res)
        return streams

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        if addon_config.get("enable_vidzee"):
            futures.append(executor.submit(_fetch_vidzee_streams))
        if addon_config.get("enable_autoembed"):
            futures.append(executor.submit(_fetch_autoembed_streams))
        if addon_config.get("enable_vixsrc"):
            futures.append(executor.submit(fetch_vixsrc_streams, tmdb_id, kind, season, episode))
        if addon_config.get("enable_superembed"):
            futures.append(executor.submit(fetch_superembed_streams, tmdb_id, kind, season, episode))

        for future in futures:
            try:
                all_streams.extend(future.result())
            except Exception as exc:
                app.logger.error("Provider fetch failed: %s", exc)

    return all_streams


def parse_stream_id(content_type, raw_id):
    """Parse Stremio content ids into a provider id + optional season/episode."""
    decoded_id = decode_stream_id(raw_id)
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
        season = normalize_episode_part(parts[2] if len(parts) > 2 else None)
        episode = normalize_episode_part(parts[3] if len(parts) > 3 else None)
        return content_id, season, episode

    imdb_id = parts[0]
    season = normalize_episode_part(parts[1] if len(parts) > 1 else None)
    episode = normalize_episode_part(parts[2] if len(parts) > 2 else None)
    if not imdb_id.startswith("tt"):
        return None, season, episode

    content_id = get_tmdb_id(imdb_id, kind)
    return content_id, season, episode


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "*")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response


def _render_config_page(config_token=None):
    if config_token:
        initial_config = decode_addon_config_token(config_token)
    else:
        initial_config = normalize_addon_config(DEFAULT_ADDON_CONFIG)
    normalized_config = normalize_addon_config(initial_config)
    canonical_token = encode_addon_config(normalized_config)

    return render_template(
        "index.html",
        default_config=normalize_addon_config(DEFAULT_ADDON_CONFIG),
        initial_config=normalized_config,
        config_token=canonical_token,
        base_url=request.url_root.rstrip("/"),
    )


@app.route("/")
@app.route("/configure")
def index():
    return _render_config_page()


@app.route("/<config_token>/configure")
def configured_index(config_token):
    return _render_config_page(config_token)


@app.route("/manifest.json")
def manifest():
    return jsonify(_build_manifest(normalize_addon_config(DEFAULT_ADDON_CONFIG)))


@app.route("/<config_token>/manifest.json")
def manifest_with_config(config_token):
    addon_config = decode_addon_config_token(config_token)
    return jsonify(_build_manifest(addon_config))


def _catalog_response(catalog_type, catalog_id, addon_config, skip=None):
    if catalog_type != "series":
        return jsonify({"metas": []})

    # Famelack Catalogs
    if catalog_id.startswith("famelack-"):
        code = catalog_id.replace("famelack-", "")
        allowed = addon_config.get("famelack_countries") or []
        if code.lower() not in [c.lower() for c in allowed]:
             return jsonify({"metas": []})

        if skip is None:
            try:
                skip = int(request.args.get("skip", "0"))
            except Exception:
                skip = 0

        metas = get_famelack_catalog(code, skip=skip)
        return jsonify({"metas": metas})

    return jsonify({"metas": []})


def _meta_response(content_type, raw_id, addon_config):
    if content_type != "series":
        return jsonify({"meta": None}), 404

    decoded_id = decode_stream_id(raw_id)

    if str(decoded_id).startswith("famelack:"):
        meta = get_famelack_meta(decoded_id)
        if not isinstance(meta, dict):
            return jsonify({"meta": None}), 404
        return jsonify({"meta": meta})

    return jsonify({"meta": None}), 404


@app.route("/catalog/<type>/<id>.json")
def catalog(type, id):
    addon_config = normalize_addon_config(DEFAULT_ADDON_CONFIG)
    return _catalog_response(type, id, addon_config)


@app.route("/catalog/<type>/<id>/skip=<int:skip>.json")
def catalog_with_skip(type, id, skip):
    addon_config = normalize_addon_config(DEFAULT_ADDON_CONFIG)
    return _catalog_response(type, id, addon_config, skip=skip)


@app.route("/<config_token>/catalog/<type>/<id>.json")
def catalog_with_config(config_token, type, id):
    addon_config = decode_addon_config_token(config_token)
    return _catalog_response(type, id, addon_config)


@app.route("/<config_token>/catalog/<type>/<id>/skip=<int:skip>.json")
def catalog_with_config_and_skip(config_token, type, id, skip):
    addon_config = decode_addon_config_token(config_token)
    return _catalog_response(type, id, addon_config, skip=skip)


@app.route("/meta/<type>/<path:id>.json")
def meta(type, id):
    addon_config = normalize_addon_config(DEFAULT_ADDON_CONFIG)
    return _meta_response(type, id, addon_config)


@app.route("/<config_token>/meta/<type>/<path:id>.json")
def meta_with_config(config_token, type, id):
    addon_config = decode_addon_config_token(config_token)
    return _meta_response(type, id, addon_config)


@app.route("/api/famelack/countries")
def api_famelack_countries():
    countries = get_famelack_countries()
    result = []
    for code, data in countries.items():
        result.append({
            "code": code,
            "name": data.get("country", code),
            "hasChannels": data.get("hasChannels", False)
        })
    result.sort(key=lambda x: x["name"])
    return jsonify(result)


def _stream_response(content_type, raw_id, addon_config):
    decoded_id = decode_stream_id(raw_id)
    parts = [p for p in decoded_id.split(":") if p]
    kind = (content_type or "").lower()
    prefix = (parts[0] if parts else "").lower()

    if prefix == "famelack":
        streams = get_famelack_streams(decoded_id)
        streams.append(_support_stream())
        return jsonify({"streams": streams})

    if prefix in ("aniways", "kitsu"):
        if not addon_config.get("enable_aniways"):
            return jsonify({"streams": []})

        source_prefix = prefix
        source_id = parts[1] if len(parts) > 1 else None
        season = normalize_episode_part(parts[2] if len(parts) > 3 else None)
        if len(parts) > 3:
            aniways_episode = normalize_episode_part(parts[3])
        else:
            aniways_episode = normalize_episode_part(parts[2] if len(parts) > 2 else None)

        if not source_id or not aniways_episode:
            return jsonify({"streams": []})

        anime_id = source_id
        if source_prefix == "kitsu":
            anime_id = resolve_aniways_id_from_kitsu(source_id)

        if not anime_id:
            return jsonify({"streams": []})

        aniways_streams = fetch_aniways_streams(anime_id, aniways_episode)
        wyzie_subtitles = _fetch_wyzie_for_anime_ids(
            source_prefix,
            source_id,
            anime_id,
            season,
            aniways_episode,
            addon_config,
        )
        _attach_subtitles(aniways_streams, wyzie_subtitles)
        aniways_streams.sort(key=lambda s: (str(s.get("name", "")), str(s.get("title", ""))))
        aniways_streams.append(_support_stream())
        return jsonify({"streams": aniways_streams})

    tmdb_id, season, episode = parse_stream_id(content_type, raw_id)
    if not tmdb_id:
        return jsonify({"streams": []})

    if kind in ("series", "tv") and (not season or not episode):
        raw_imdb = parts[0] if parts else ""
        if raw_imdb.startswith("tt"):
            _, hint_season, hint_episode = get_series_context_from_imdb(raw_imdb)
            if not season and hint_season is not None:
                season = str(hint_season)
            if not episode and hint_episode is not None:
                episode = str(hint_episode)

    if kind in ("series", "tv") and (not season or not episode):
        return jsonify({"streams": []})

    with ThreadPoolExecutor(max_workers=2) as executor:
        provider_future = executor.submit(
            _fetch_provider_streams,
            tmdb_id,
            kind,
            season,
            episode,
            addon_config,
        )
        wyzie_future = executor.submit(
            _fetch_wyzie_for_regular_content,
            tmdb_id,
            kind,
            season,
            episode,
            addon_config,
        )
        try:
            all_streams = provider_future.result()
        except Exception as exc:
            app.logger.error("Provider fetch group failed: %s", exc)
            all_streams = []
        try:
            wyzie_subtitles = wyzie_future.result()
        except Exception as exc:
            app.logger.error("Wyzie fetch failed: %s", exc)
            wyzie_subtitles = []

    _attach_subtitles(all_streams, wyzie_subtitles)

    all_streams.sort(key=lambda s: (provider_rank(s), str(s.get("name", "")), str(s.get("title", ""))))
    all_streams.append(_support_stream())
    return jsonify({"streams": all_streams})


@app.route("/stream/<type>/<path:id>.json")
def stream(type, id):
    return _stream_response(type, id, normalize_addon_config(DEFAULT_ADDON_CONFIG))


@app.route("/<config_token>/stream/<type>/<path:id>.json")
def stream_with_config(config_token, type, id):
    addon_config = decode_addon_config_token(config_token)
    return _stream_response(type, id, addon_config)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
