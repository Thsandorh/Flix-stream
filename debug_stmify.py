import requests
import re
import json

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://stmify.com/",
    "Origin": "https://stmify.com"
}

IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

def test_pagination():
    print("--- Testing Pagination ---")
    url = "https://stmify.com/live-tv/page/2/"
    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        if r.status_code == 200:
            count = len(re.findall(r'class="archive-item"', r.text))
            print(f"Page 2 items: {count}")
        else:
            print(f"Page 2 failed: {r.status_code}")
    except Exception as e:
        print(f"Pagination error: {e}")

def resolve_stream(slug, user_agent=None):
    print(f"\n--- Resolving {slug} (UA: {'iPhone' if user_agent == IPHONE_UA else 'Desktop'}) ---")
    channel_url = f"https://stmify.com/live-tv/{slug}/"
    ua = user_agent or COMMON_HEADERS["User-Agent"]
    headers = COMMON_HEADERS.copy()
    headers["User-Agent"] = ua

    try:
        r = requests.get(channel_url, headers=headers, timeout=10)
        iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', r.text)
        if not iframe_match:
            iframe_match = re.search(r'src="(https://cdn\.stmify\.com/embed[^"]+)"', r.text)

        if not iframe_match:
            print("No iframe found.")
            return

        iframe_src = iframe_match.group(1)
        if iframe_src.startswith("//"):
            iframe_src = "https:" + iframe_src
        print(f"Iframe: {iframe_src}")

        headers["Referer"] = channel_url
        r_embed = requests.get(iframe_src, headers=headers, timeout=10)

        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', r_embed.text)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', r_embed.text)

        if not stream_id_match or not country_match:
            print("Could not extract streamId/country.")
            return

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)
        print(f"Key: {stream_key}, Country: {country}")

        api_url = f"https://cdn.stmify.com/embed-free/fetch_streams.php?country={country}"
        api_headers = headers.copy()
        api_headers["Referer"] = iframe_src
        api_headers["X-Requested-With"] = "XMLHttpRequest"

        r_api = requests.get(api_url, headers=api_headers, timeout=10)
        data = r_api.json()

        if stream_key in data:
            print(json.dumps(data[stream_key], indent=2))
        else:
            print("Stream key not in API response.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pagination()
    resolve_stream("tv1") # Desktop
    resolve_stream("tv1", IPHONE_UA) # Mobile
    resolve_stream("nhl-network")
    resolve_stream("galaxy")
