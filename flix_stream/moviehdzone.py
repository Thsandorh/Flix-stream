import logging
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup

from flix_stream.config import COMMON_HEADERS

logger = logging.getLogger(__name__)

BASE_URL = "https://moviehdzone.com"
SEARCH_API_URL = f"{BASE_URL}/searching"

# Use common headers but add referer for MovieHDZone
MOVIEHDZONE_HEADERS = COMMON_HEADERS.copy()
MOVIEHDZONE_HEADERS.update({
    "Referer": f"{BASE_URL}/",
    "Origin": BASE_URL
    # Remove X-Requested-With for page scraping
})

def search_moviehdzone(query):
    """
    Search MovieHDZone.
    First try API, if fails (non-JSON), fall back to scraping search page.
    """
    # 1. Try API (often blocked)
    params = {"q": query, "limit": 10, "offset": 0}
    try:
        api_headers = MOVIEHDZONE_HEADERS.copy()
        api_headers["X-Requested-With"] = "XMLHttpRequest"
        response = requests.get(SEARCH_API_URL, params=params, headers=api_headers, timeout=10)
        if response.status_code == 200:
            try:
                data = response.json()
                return data.get("data", [])
            except ValueError:
                pass # Not JSON, fall back
    except Exception:
        pass

    # 2. Scrape Search Page
    # URL: /search/Query/
    # Note: Query usually needs to be space->plus or similar.
    # Standard is /search/Query%20Here/
    encoded_query = quote(query)
    scrape_url = f"{BASE_URL}/search/{encoded_query}/"

    hits = []
    try:
        response = requests.get(scrape_url, headers=MOVIEHDZONE_HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Look for result cards
            # Based on previous dump: <div class="card border-0 shadow"><a href=... class="rounded poster">...<h2 class="card-title ...">Title</h2>
            for card in soup.find_all('div', class_='card'):
                a_tag = card.find('a', class_='poster')
                if not a_tag:
                    continue

                href = a_tag.get('href')
                if not href:
                    continue

                title_tag = card.find('h2', class_='card-title')
                title = title_tag.text.strip() if title_tag else "Unknown"

                # Extract slug from href
                # href might be /movie/slug/ or /movie/slug.html
                # We need the "s" (slug) for consistency, or just use the full href.
                # The API returns 's'. We can adapt get_streams to take slug OR url.

                # Normalize href
                if href.startswith("/"):
                    # Remove leading / and potential movie/ prefix if we want pure slug?
                    # API said "s": "slug". URL is /movie/slug.html
                    # Let's verify href format.
                    pass

                hits.append({
                    "t": title,
                    "url": href # Store full relative URL
                })
    except Exception as exc:
        logger.error("MovieHDZone page scrape failed: %s", exc)

    return hits

def get_moviehdzone_streams(title, season=None, episode=None):
    """
    Fetch streams for MovieHDZone.
    """
    hits = search_moviehdzone(title)
    if not hits:
        return []

    streams = []
    for hit in hits:
        hit_title = hit.get("t")
        hit_url = hit.get("url") # Relative URL from scrape OR None from API
        slug = hit.get("s") # From API

        if title.lower() not in hit_title.lower():
            continue

        if hit_url:
            url = f"{BASE_URL}{hit_url}" if hit_url.startswith("/") else hit_url
        elif slug:
            url = f"{BASE_URL}/movie/{slug}.html" # Guessing .html based on JS
        else:
            continue

        streams.append({
            "name": "MovieHDZone",
            "title": f"{hit_title} (Open Website)",
            "url": url,
            "behaviorHints": {
                "notWebReady": True,
                "proxyHeaders": {"request": MOVIEHDZONE_HEADERS}
            }
        })

    return streams

def fetch_moviehdzone_streams_worker(tmdb_id, title, season=None, episode=None):
    """Worker for provider integration."""
    return get_moviehdzone_streams(title, season, episode)
