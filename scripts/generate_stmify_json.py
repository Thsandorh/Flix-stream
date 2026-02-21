import requests
import re
import json
import os
import concurrent.futures
from urllib.parse import urlparse

STMIFY_BASE_URL = "https://stmify.com"
CDN_BASE_URL = "https://cdn.stmify.com"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'stmify_channels.json')

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": STMIFY_BASE_URL + "/",
    "Origin": STMIFY_BASE_URL
}

def resolve_stream_info(slug):
    channel_url = f"{STMIFY_BASE_URL}/live-tv/{slug}/"
    try:
        # Step 1: Get Channel Page
        r = requests.get(channel_url, headers=COMMON_HEADERS, timeout=10)
        if r.status_code != 200:
            return None

        # Step 2: Find Iframe Source
        iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', r.text)
        if not iframe_match:
            iframe_match = re.search(r'src="(https://cdn\.stmify\.com/embed[^"]+)"', r.text)

        if not iframe_match:
            return None

        iframe_src = iframe_match.group(1)
        if iframe_src.startswith("//"):
            iframe_src = "https:" + iframe_src

        # Step 3: Fetch Embed Page
        headers = COMMON_HEADERS.copy()
        headers["Referer"] = channel_url

        r_embed = requests.get(iframe_src, headers=headers, timeout=10)
        if r_embed.status_code != 200:
            return None

        # Step 4: Extract streamId and country
        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', r_embed.text)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', r_embed.text)

        if not stream_id_match or not country_match:
            return None

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)

        # Step 5: Call API
        api_url = f"{CDN_BASE_URL}/embed-free/fetch_streams.php?country={country}"
        api_headers = COMMON_HEADERS.copy()
        api_headers["Referer"] = iframe_src
        api_headers["X-Requested-With"] = "XMLHttpRequest"

        r_api = requests.get(api_url, headers=api_headers, timeout=10)
        if r_api.status_code != 200:
            return None

        data = r_api.json()
        if stream_key in data:
            item = data[stream_key]
            # Return dict with url and keys
            return {
                "url": item.get("url"),
                "k1": item.get("k1"),
                "k2": item.get("k2")
            }

    except Exception as e:
        print(f"Error resolving {slug}: {e}")
        return None
    return None

def scrape_page(page):
    url = f"{STMIFY_BASE_URL}/live-tv/"
    if page > 1:
        url = f"{STMIFY_BASE_URL}/live-tv/page/{page}/"

    print(f"Scraping page {page}...")
    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=15)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            print(f"Page {page} failed with {r.status_code}")
            return []

        html = r.text
        channels = []
        items = html.split('class="archive-item"')
        for item in items[1:]:
            link_match = re.search(r'<a\s+href="([^"]+)"', item)
            if not link_match: continue
            link = link_match.group(1)

            slug_match = re.search(r'/live-tv/([^/]+)/', link)
            if not slug_match: continue
            slug = slug_match.group(1)

            img_match = re.search(r'<img[^>]+src="([^"]+)"', item)
            data_src_match = re.search(r'<img[^>]+data-src="([^"]+)"', item)

            poster = None
            if data_src_match:
                poster = data_src_match.group(1)
            elif img_match:
                poster = img_match.group(1)

            title_match = re.search(r'<img[^>]+alt="([^"]+)"', item)
            name = slug.replace("-", " ").title()
            if title_match:
                name = title_match.group(1)

            channels.append({
                "id": f"stmify:{slug}",
                "slug": slug,
                "type": "series",
                "name": name,
                "poster": poster,
                "description": f"Watch {name} live on Stmify."
            })
        return channels
    except Exception as e:
        print(f"Error scraping page {page}: {e}")
        return []

def main():
    all_channels = []
    page = 1

    # Scrape catalog first
    while True:
        channels = scrape_page(page)
        if not channels:
            break
        all_channels.extend(channels)
        print(f"Found {len(channels)} channels on page {page}. Total: {len(all_channels)}")
        page += 1
        if page > 50:
            print("Max pages reached.")
            break

    print(f"Scraped {len(all_channels)} channels. Resolving streams...")

    # Resolve streams concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_channel = {executor.submit(resolve_stream_info, ch["slug"]): ch for ch in all_channels}

        count = 0
        total = len(all_channels)

        for future in concurrent.futures.as_completed(future_to_channel):
            channel = future_to_channel[future]
            try:
                info = future.result()
                if info and info.get("url"):
                    channel["stream_url"] = info["url"]
                    if info.get("k1"):
                        channel["k1"] = info["k1"]
                    if info.get("k2"):
                        channel["k2"] = info["k2"]
                    print(f"[{count}/{total}] Resolved {channel['slug']}")
                else:
                    print(f"[{count}/{total}] Failed to resolve {channel['slug']}")
            except Exception as exc:
                print(f"[{count}/{total}] Exception for {channel['slug']}: {exc}")
            count += 1

    valid_channels = [c for c in all_channels if c.get("stream_url")]
    print(f"Resolved {len(valid_channels)} out of {len(all_channels)} channels.")

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(valid_channels, f, indent=2)

    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
