import datetime
import logging
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from flix_stream.config import COMMON_HEADERS

logger = logging.getLogger(__name__)

BASE_URL = "https://new3.hdhub4u.fo"
SEARCH_API_URL = "https://search.pingora.fyi/collections/post/documents/search"

# Use the same headers as main app but add Referer/Origin for HDHub4u
HDHUB_HEADERS = COMMON_HEADERS.copy()
HDHUB_HEADERS.update({
    "Referer": f"{BASE_URL}/",
    "Origin": BASE_URL,
})


def search_hdhub4u(query):
    """Search HDHub4u using the external search API."""
    today = datetime.date.today().isoformat()
    params = {
        'q': query,
        'query_by': 'post_title,category,stars,director,imdb_id',
        'query_by_weights': '4,2,2,2,4',
        'sort_by': 'sort_by_date:desc',
        'limit': '15',
        'highlight_fields': 'none',
        'use_cache': 'true',
        'page': '1',
        'analytics_tag': today
    }

    try:
        response = requests.get(SEARCH_API_URL, params=params, headers=HDHUB_HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("hits", [])
    except Exception as exc:
        logger.error("HDHub4u search failed: %s", exc)
    return []


def resolve_gadgetsweb(url):
    """
    Attempt to resolve gadgetsweb.xyz links to their destination.
    These links often redirect to cryptoinsights.site or similar.
    We return the final URL after following redirects.
    """
    try:
        session = requests.Session()
        session.headers.update(HDHUB_HEADERS)

        # Follow redirects
        resp = session.get(url, allow_redirects=True, timeout=10)
        final_url = resp.url

        # Check if failed (cryptoinsights text)
        if "Failed to decode link" in resp.text:
            # We return the intermediate URL, user might try opening it in browser
            return final_url

        return final_url
    except Exception as exc:
        logger.error("HDHub4u gadgetsweb resolution failed: %s", exc)
        return url


def resolve_hdstream4u(url):
    """
    Attempt to resolve hdstream4u links to direct file.
    This often requires ReCAPTCHA, so it might fail.
    """
    try:
        session = requests.Session()
        session.headers.update(HDHUB_HEADERS)

        # Step 1: GET page
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return url

        soup = BeautifulSoup(resp.text, 'html.parser')
        form = soup.find('form')
        if not form:
            return url

        inputs = form.find_all('input')
        data = {i.get('name'): i.get('value') for i in inputs if i.get('name')}

        # Step 2: POST
        action = form.get('action')
        post_url = url
        if action:
            if action.startswith('http'):
                post_url = action
            elif action.startswith('/'):
                parsed = requests.utils.urlparse(url)
                post_url = f"{parsed.scheme}://{parsed.netloc}{action}"

        resp2 = session.post(post_url, data=data, allow_redirects=False, timeout=10)
        if resp2.status_code == 302:
            return resp2.headers.get('Location')

        return url
    except Exception as exc:
        logger.error("HDHub4u hdstream resolution failed: %s", exc)
        return url


def get_hdhub4u_links(permalink, season=None, episode=None):
    """Scrape the movie/series page for links."""
    url = f"{BASE_URL}{permalink}"
    links = []

    try:
        response = requests.get(url, headers=HDHUB_HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Regex to find episode text like "EPiSODE 1" or "E01"
        ep_pattern = re.compile(r'EPiSODE\s*(\d+)', re.IGNORECASE)

        # Iterate over all 'h3' or 'h4' tags which usually contain the links
        for tag in soup.find_all(['h3', 'h4']):
            text = tag.get_text(separator=' ', strip=True)

            # Check for episode match if season/episode is provided
            ep_match = ep_pattern.search(text)
            current_ep = ep_match.group(1) if ep_match else None

            # If we are looking for a specific episode, we prioritize exact matches.
            # If the tag has an episode number that doesn't match, skip it.
            if season and episode and current_ep:
                if int(current_ep) != int(episode):
                    continue

            is_pack = False
            if season and episode and not current_ep:
                is_pack = True

            # Extract links within this tag
            for a in tag.find_all('a', href=True):
                href = a['href']
                link_text = a.text.strip() or "Link"

                stream_type = "Download"
                provider_name = "Download"

                if "hdstream4u.com" in href:
                    stream_type = "Watch"
                    provider_name = "HDStream4u"
                elif "gadgetsweb.xyz" in href:
                    stream_type = "HubDrive"
                    provider_name = "HubDrive"
                else:
                    # Skip other links unless they look promising
                    continue

                # Title formatting
                title_parts = [f"[{provider_name}]"]

                if current_ep:
                    title_parts.append(f"Ep {current_ep}")
                elif is_pack:
                    title_parts.append("Pack/Full")

                if link_text:
                    title_parts.append(link_text)

                final_title = " ".join(title_parts)

                # Resolve links
                final_url = href
                if stream_type == "HubDrive":
                    final_url = resolve_gadgetsweb(href)
                elif stream_type == "Watch":
                    # Try to resolve HDStream4u (Watch links often are direct if resolved)
                    # Note: These are often protected by captcha, resolution might fail and return original URL
                    resolved = resolve_hdstream4u(href)
                    if resolved and resolved != href:
                        final_url = resolved

                links.append({
                    "name": f"HDHub4u {stream_type}",
                    "title": final_title,
                    "url": final_url,
                    "behaviorHints": {
                        "notWebReady": True,
                        "proxyHeaders": {"request": HDHUB_HEADERS}
                    }
                })

    except Exception as exc:
        logger.error("HDHub4u page scrape failed: %s", exc)

    return links


def fetch_hdhub4u_streams(tmdb_id, imdb_id, title, season=None, episode=None):
    """Main orchestration function to fetch streams from HDHub4u."""
    # 1. Search
    query = imdb_id if imdb_id else title
    if not query:
        return []

    hits = search_hdhub4u(query)

    if not hits and season and title and not imdb_id:
         hits = search_hdhub4u(f"{title} Season {season}")

    if not hits:
        return []

    # 2. Select best match
    best_hit = None

    if imdb_id:
        for hit in hits:
            doc = hit.get('document', {})
            if doc.get('imdb_id') == imdb_id:
                best_hit = doc
                break

    if not best_hit and title:
        for hit in hits:
            doc = hit.get('document', {})
            post_title = doc.get('post_title', '').lower()
            if title.lower() in post_title:
                if season:
                    if f"season {season}" in post_title or f"s{int(season):02d}" in post_title:
                        best_hit = doc
                        break
                else:
                    best_hit = doc
                    break

    if not best_hit:
        return []

    permalink = best_hit.get('permalink')
    if not permalink:
        return []

    # 3. Extract links
    return get_hdhub4u_links(permalink, season, episode)
