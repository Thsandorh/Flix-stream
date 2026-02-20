import logging
from functools import lru_cache
from urllib.parse import quote_plus

import requests

from flix_stream.config import COMMON_HEADERS


logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def _build_external_id_query(mal_id=None, anilist_id=None):
    clauses = []
    if mal_id is not None:
        clauses.append(f'{{ ?item wdt:P4086 "{int(mal_id)}". }}')
    if anilist_id is not None:
        clauses.append(f'{{ ?item wdt:P8729 "{int(anilist_id)}". }}')
    if not clauses:
        return None

    union = " UNION ".join(clauses)
    return (
        "SELECT ?item ?imdb ?tmdbTv ?tmdbMovie WHERE { "
        f"{union} "
        "OPTIONAL { ?item wdt:P345 ?imdb } "
        "OPTIONAL { ?item wdt:P4983 ?tmdbTv } "
        "OPTIONAL { ?item wdt:P4947 ?tmdbMovie } "
        "} LIMIT 20"
    )


@lru_cache(maxsize=2048)
def resolve_external_ids_from_mal_anilist(mal_id=None, anilist_id=None):
    """Resolve TMDB/IMDb ids from MAL/AniList ids via Wikidata."""
    query = _build_external_id_query(mal_id, anilist_id)
    if not query:
        return []

    url = f"{WIKIDATA_SPARQL_ENDPOINT}?format=json&query={quote_plus(query)}"
    headers = {
        "User-Agent": COMMON_HEADERS["User-Agent"],
        "Accept": "application/sparql-results+json, application/json",
    }
    try:
        payload = requests.get(url, headers=headers, timeout=10).json()
        rows = payload.get("results", {}).get("bindings", [])
    except Exception as exc:
        logger.error("Wikidata lookup failed for MAL=%s AniList=%s: %s", mal_id, anilist_id, exc)
        return []

    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        imdb_id = row.get("imdb", {}).get("value")
        tmdb_tv = row.get("tmdbTv", {}).get("value")
        tmdb_movie = row.get("tmdbMovie", {}).get("value")

        try:
            tmdb_tv = int(tmdb_tv) if tmdb_tv is not None else None
        except Exception:
            tmdb_tv = None
        try:
            tmdb_movie = int(tmdb_movie) if tmdb_movie is not None else None
        except Exception:
            tmdb_movie = None

        parsed.append(
            {
                "imdb_id": str(imdb_id).strip() if imdb_id else None,
                "tmdb_tv_id": tmdb_tv,
                "tmdb_movie_id": tmdb_movie,
            }
        )

    return parsed


def pick_best_tmdb_candidate(candidates, hint=None):
    """Pick best candidate from Wikidata rows with a type preference."""
    if not candidates:
        return None, None, None

    normalized_hint = str(hint or "").lower().strip()

    def _prefer_by_hint():
        if normalized_hint in ("movie", "film"):
            movie_rows = [item for item in candidates if item.get("tmdb_movie_id") is not None]
            if movie_rows:
                best = sorted(movie_rows, key=lambda item: 1 if item.get("imdb_id") else 0, reverse=True)[0]
                return int(best["tmdb_movie_id"]), "movie", best.get("imdb_id")
        if normalized_hint in ("tv", "series", "show"):
            tv_rows = [item for item in candidates if item.get("tmdb_tv_id") is not None]
            if tv_rows:
                best = sorted(tv_rows, key=lambda item: 1 if item.get("imdb_id") else 0, reverse=True)[0]
                return int(best["tmdb_tv_id"]), "tv", best.get("imdb_id")
        return None

    hinted = _prefer_by_hint()
    if hinted:
        return hinted

    order = ("tmdb_tv_id", "tmdb_movie_id", "imdb_id")

    def _score(item):
        score = 0
        if item.get("tmdb_tv_id") is not None:
            score += 30
        if item.get("tmdb_movie_id") is not None:
            score += 30
        if item.get("imdb_id"):
            score += 20

        return score

    ranked = sorted(candidates, key=_score, reverse=True)
    top = ranked[0]
    for key in order:
        value = top.get(key)
        if value is None:
            continue
        if key == "tmdb_tv_id":
            return int(value), "tv", top.get("imdb_id")
        if key == "tmdb_movie_id":
            return int(value), "movie", top.get("imdb_id")
        return None, None, str(value).strip()
    return None, None, top.get("imdb_id")
