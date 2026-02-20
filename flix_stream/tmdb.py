import logging
from functools import lru_cache

import requests

from flix_stream.config import COMMON_HEADERS, TMDB_TOKEN


logger = logging.getLogger(__name__)


@lru_cache(maxsize=2048)
def get_tmdb_id(imdb_id, content_type=None):
    """Maps IMDb id to TMDB id with type-aware selection."""
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}", "User-Agent": COMMON_HEADERS["User-Agent"]}
    kind = (content_type or "").lower()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        movie_results = data.get("movie_results") or []
        tv_results = data.get("tv_results") or []
        tv_episode_results = data.get("tv_episode_results") or []
        tv_season_results = data.get("tv_season_results") or []
        tv_season_show_id = next(
            (item.get("show_id") for item in tv_season_results if item.get("show_id")),
            None,
        )

        if kind in ("series", "tv"):
            if tv_results:
                return tv_results[0]["id"]
            if tv_episode_results and tv_episode_results[0].get("show_id"):
                return tv_episode_results[0]["show_id"]
            if tv_season_show_id:
                return tv_season_show_id
            return None

        if kind == "movie":
            if movie_results:
                return movie_results[0]["id"]
            return None

        # Fallback if type is unknown.
        if movie_results:
            return movie_results[0]["id"]
        if tv_results:
            return tv_results[0]["id"]
        if tv_episode_results and tv_episode_results[0].get("show_id"):
            return tv_episode_results[0]["show_id"]
        if tv_season_show_id:
            return tv_season_show_id
    except Exception as exc:
        logger.error("TMDB mapping failed for %s: %s", imdb_id, exc)

    # Fallback: Cinemeta often still exposes moviedb_id when TMDB /find misses.
    fallback_tmdb_id = get_tmdb_id_from_cinemeta(imdb_id, kind)
    if fallback_tmdb_id:
        return fallback_tmdb_id

    return None


@lru_cache(maxsize=2048)
def get_tmdb_id_from_cinemeta(imdb_id, content_type=None):
    """Fallback IMDb->TMDB mapping via Cinemeta meta endpoint."""
    kind = (content_type or "").lower()
    if kind in ("series", "tv"):
        meta_types = ["series"]
    elif kind == "movie":
        meta_types = ["movie"]
    else:
        meta_types = ["movie", "series"]

    headers = {"User-Agent": COMMON_HEADERS["User-Agent"]}
    for meta_type in meta_types:
        url = f"https://v3-cinemeta.strem.io/meta/{meta_type}/{imdb_id}.json"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                continue
            data = response.json()
            meta = data.get("meta") if isinstance(data, dict) else None
            moviedb_id = meta.get("moviedb_id") if isinstance(meta, dict) else None
            if moviedb_id is None:
                continue
            return int(moviedb_id)
        except Exception:
            continue

    return None


@lru_cache(maxsize=2048)
def get_series_context_from_imdb(imdb_id):
    """Resolve show/season/episode context from an IMDb episode id."""
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}", "User-Agent": COMMON_HEADERS["User-Agent"]}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        tv_episode_results = data.get("tv_episode_results") or []
        if tv_episode_results:
            item = tv_episode_results[0]
            return item.get("show_id"), item.get("season_number"), item.get("episode_number")

        tv_season_results = data.get("tv_season_results") or []
        if tv_season_results:
            item = tv_season_results[0]
            return item.get("show_id"), item.get("season_number"), None
    except Exception as exc:
        logger.error("TMDB series context lookup failed for %s: %s", imdb_id, exc)

    return None, None, None
