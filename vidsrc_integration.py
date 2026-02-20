import requests
import re
import json
from concurrent.futures import ThreadPoolExecutor

# List of domains from vidsrc.domains
VIDSRC_DOMAINS = [
    "https://vidsrcme.ru",
    "https://vidsrcme.su",
    "https://vidsrc-me.ru",
    "https://vidsrc-me.su",
    "https://vidsrc-embed.ru",
    "https://vidsrc-embed.su",
    "https://vsrc.su",
    # Fallback/Old
    "https://vidsrc.me",
    "https://vidsrc.net",
    "https://vidsrc.xyz",
    "https://vidsrc.io"
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://vidsrcme.ru/",
}

def get_working_domain():
    """Checks domains to find a working one."""
    for domain in VIDSRC_DOMAINS:
        try:
            r = requests.head(domain, headers=COMMON_HEADERS, timeout=3)
            if r.status_code < 500:
                return domain
        except Exception:
            continue
    return VIDSRC_DOMAINS[0] # Fallback

def get_vidsrc_stream(tmdb_id, season=None, episode=None):
    """
    Fetches the stream info for Vidsrc.me.

    Flow:
    1. Embed Page: https://{domain}/embed/{id}
    2. Extract Hash: <div class="server" data-hash="...">
    3. RCP Redirect: https://cloudnestra.com/rcp/{hash}
    4. PRORCP Page: https://cloudnestra.com/prorcp/{hash} (Requires Turnstile)
    5. Player Config: Extracted from PRORCP page (Playerjs)

    Args:
        tmdb_id: TMDB ID (or IMDB ID if prefixed with 'tt')
        season: Season number
        episode: Episode number
    """
    domain = get_working_domain()

    # Construct Embed URL
    # Vidsrc accepts IMDB ID usually. If TMDB ID is passed, might need conversion if it's numeric.
    # Assuming the input `id` is compatible (e.g. tt1234567).
    # If using TMDB ID for movies: embed/movie?tmdb=... (uncommon)
    # Standard format: embed/{imdb_id}

    # Note: If passing TMDB ID, Vidsrc might not support it directly in the path /embed/123.
    # It usually expects IMDB ID (tt...).
    # If `tmdb_id` is numeric, this script assumes it needs an IMDB ID or the caller passes 'tt...'.

    url = f"{domain}/embed/{tmdb_id}"
    if season and episode:
        url += f"/{season}-{episode}"

    print(f"Fetching embed: {url}")

    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()

        # Parse Servers
        # Look for "VidSrc PRO" or similar high-quality server
        # Regex to find data-hash
        # <div class="server" data-hash="...">...</div>

        # Example: <div class="server" data-hash="...:...">CloudStream Pro</div>

        hashes = re.findall(r'<div class="server"\s+data-hash="([^"]+)">([^<]+)</div>', r.text)

        target_hash = None
        for h, name in hashes:
            print(f"Found server: {name}")
            if "VidSrc PRO" in name or "CloudStream" in name:
                target_hash = h
                break

        if not target_hash and hashes:
            target_hash = hashes[0][0]

        if not target_hash:
            print("No server hash found.")
            return None

        print(f"Target Hash: {target_hash[:20]}...")

        # Step 3: RCP Redirect
        # The embed script constructs: //cloudnestra.com/rcp/ + hash
        rcp_url = f"https://cloudnestra.com/rcp/{target_hash}"

        # IMPORTANT: Referer must be the embed page
        headers = COMMON_HEADERS.copy()
        headers["Referer"] = url

        print(f"Fetching RCP: {rcp_url}")
        r_rcp = requests.get(rcp_url, headers=headers, timeout=10)

        if r_rcp.status_code != 200:
            print(f"RCP request failed: {r_rcp.status_code}")
            return None

        # Step 4: Extract PRORCP URL
        # The response is HTML with an iframe src or a script that loads the next step.
        # Pattern: src: '/prorcp/...'

        match = re.search(r"src:\s*['\"]/prorcp/([^'\"]+)['\"]", r_rcp.text)
        if match:
            prorcp_hash = match.group(1)
            prorcp_url = f"https://cloudnestra.com/prorcp/{prorcp_hash}"
            print(f"Found PRORCP URL: {prorcp_url}")

            # Step 5: Handling Cloudflare Turnstile
            # The PRORCP page is protected by Cloudflare Turnstile.
            # Automated requests (curl/requests) will likely get a 403 or a Challenge page.
            #
            # ACTION REQUIRED FOR AGENT:
            # 1. Use a browser automation tool (Playwright/Selenium) or a Turnstile solver.
            # 2. Verify the Turnstile token via POST /rcp_verify (if handled by page JS).
            # 3. Upon success, the page loads the player config.
            #
            # The player config (Playerjs) usually contains:
            # file: "/list/{hash}.js" or direct HLS URL.

            print("\n!!! BLOCKER: Cloudflare Turnstile detected on PRORCP page. !!!")
            print("The following steps require browser emulation or a solver:")
            print(f"1. Open {prorcp_url} with Referer: {rcp_url}")
            print("2. Solve Turnstile.")
            print("3. Extract 'file' from Playerjs config or 'source' from network traffic.")

            return {
                "status": "requires_solver",
                "next_url": prorcp_url,
                "referer": rcp_url
            }

        else:
            print("Could not find PRORCP URL in RCP response.")
            # It might be a different format or direct redirect
            return None

    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    # Test with Shawshank Redemption (IMDB: tt0111161)
    get_vidsrc_stream("tt0111161")
