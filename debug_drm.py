import requests
import re
import json

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://stmify.com/",
    "Origin": "https://stmify.com"
}

def check_channel(slug):
    print(f"Checking {slug}...")
    channel_url = f"https://stmify.com/live-tv/{slug}/"
    try:
        r = requests.get(channel_url, headers=COMMON_HEADERS, timeout=10)
        iframe_match = re.search(r'src="(//cdn\.stmify\.com/embed[^"]+)"', r.text)
        if not iframe_match:
            print("No iframe found.")
            return

        iframe_src = iframe_match.group(1)
        if iframe_src.startswith("//"):
            iframe_src = "https:" + iframe_src
        print(f"Iframe: {iframe_src}")

        headers = COMMON_HEADERS.copy()
        headers["Referer"] = channel_url
        r_embed = requests.get(iframe_src, headers=headers, timeout=10)

        stream_id_match = re.search(r'const\s+streamId\s*=\s*"([^"]+)"', r_embed.text)
        country_match = re.search(r'const\s+country\s*=\s*"([^"]+)"', r_embed.text)

        if not stream_id_match or not country_match:
            print("No streamId/country.")
            return

        stream_key = stream_id_match.group(1)
        country = country_match.group(1)

        api_url = f"https://cdn.stmify.com/embed-free/fetch_streams.php?country={country}"
        api_headers = headers.copy()
        api_headers["Referer"] = iframe_src
        api_headers["X-Requested-With"] = "XMLHttpRequest"

        r_api = requests.get(api_url, headers=api_headers, timeout=10)
        data = r_api.json()

        if stream_key in data:
            print(json.dumps(data[stream_key], indent=2))
        else:
            print("Key not found in API.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_channel("disney-channel")
    check_channel("hbo")
