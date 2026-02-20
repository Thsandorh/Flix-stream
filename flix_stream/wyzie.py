import logging

import requests

from flix_stream.config import WYZIE_API_BASE, WYZIE_COMMON_HEADERS


logger = logging.getLogger(__name__)


def _prepare_wyzie_params(content_id, season, episode, addon_config):
    params = {"id": str(content_id)}

    if season and episode:
        params["season"] = str(season)
        params["episode"] = str(episode)

    languages = addon_config.get("wyzie_languages") or []
    if languages:
        params["language"] = ",".join(str(lang).strip() for lang in languages if str(lang).strip())

    formats = addon_config.get("wyzie_formats") or []
    if formats:
        params["format"] = ",".join(str(fmt).strip() for fmt in formats if str(fmt).strip())

    source = str(addon_config.get("wyzie_source") or "").strip().lower()
    if source:
        params["source"] = source

    if addon_config.get("wyzie_hearing_impaired"):
        params["hi"] = "true"

    return params


def merge_subtitles(existing, extra):
    merged = []
    seen_urls = set()

    for candidate in (existing or []) + (extra or []):
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(candidate)

    return merged


def fetch_wyzie_subtitles(content_id, season, episode, addon_config):
    params = _prepare_wyzie_params(content_id, season, episode, addon_config)

    try:
        response = requests.get(
            f"{WYZIE_API_BASE}/search",
            headers=WYZIE_COMMON_HEADERS,
            params=params,
            timeout=10,
        )
        if response.status_code != 200:
            return []
        payload = response.json()
    except Exception as exc:
        logger.error("Wyzie subtitle lookup failed for id=%s: %s", content_id, exc)
        return []

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("value") or payload.get("items") or []
    else:
        return []

    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        lang = str(item.get("language") or item.get("display") or "und").strip()
        source = str(item.get("source") or "wyzie").strip()
        fmt = str(item.get("format") or "").strip()
        label = str(item.get("display") or lang or "Subtitle").strip()
        subtitle_id = f"Wyzie:{source}:{fmt}:{item.get('id') or label}"

        normalized.append(
            {
                "id": subtitle_id,
                "lang": lang,
                "url": url,
            }
        )

    # Keep API order but dedupe by URL.
    unique = merge_subtitles([], normalized)

    max_results = int(addon_config.get("wyzie_max_results") or 8)
    max_results = max(1, min(max_results, 30))
    return unique[:max_results]
