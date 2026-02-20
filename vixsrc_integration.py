import requests
import re
import json
import sys
from urllib.parse import urlencode

class VixSrcDecoder:
    """
    Decodes the VixSrc.to API to extract the direct HLS (m3u8) link.
    """

    BASE_URL = "https://vixsrc.to"
    # Use a standard browser UA to avoid being served the captcha page
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    def get_stream_url(self, tmdb_id, media_type="movie"):
        """
        Fetches the embed page and extracts the master playlist URL.
        """
        url = f"{self.BASE_URL}/{media_type}/{tmdb_id}"
        headers = {
            "User-Agent": self.USER_AGENT,
            "Referer": self.BASE_URL,
        }

        print(f"[*] Fetching {url}...", file=sys.stderr)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            return {"error": f"Failed to fetch page: {e}"}

        # Look for window.masterPlaylist object
        # It's a JS object literal in the HTML

        # Regex to capture the content inside window.masterPlaylist = { ... }
        match = re.search(r'window\.masterPlaylist\s*=\s*({.*?})\s*window\.canPlay', html, re.DOTALL)

        if not match:
             return {"error": "Could not find 'window.masterPlaylist' in HTML. The site might have changed layout or blocked the request."}

        js_obj = match.group(1)

        # Extract base URL
        url_match = re.search(r"url:\s*['\"]([^'\"]+)['\"]", js_obj)
        if not url_match:
            return {"error": "Found masterPlaylist but no URL."}

        base_playlist_url = url_match.group(1)

        # Extract params object
        params_match = re.search(r'params:\s*({.*?}),', js_obj, re.DOTALL)
        query_params = {}

        if params_match:
            raw_params = params_match.group(1)
            # Parse 'key': 'value' or 'key': value lines
            # Updated to handle unquoted values (numbers/booleans/null) if present
            # Matches: key : "value" OR key : 123
            pairs = re.findall(r"['\"]?(\w+)['\"]?:\s*(?:['\"]([^'\"]*)['\"]|([0-9\.]+))", raw_params)
            for k, v_str, v_num in pairs:
                if v_str:
                    query_params[k] = v_str
                else:
                    query_params[k] = v_num

        # Logic from vixsrc-nxIkFVjF.js:
        # i.searchParams.append("h",1);
        # i.searchParams.append("lang",h); // h defaults to "en"

        query_params["h"] = "1"
        if "lang" not in query_params:
            query_params["lang"] = "en"

        final_url = f"{base_playlist_url}?{urlencode(query_params)}"
        return {"url": final_url}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract VixSrc m3u8 link")
    parser.add_argument("id", nargs='?', help="TMDB ID", default="27205")
    parser.add_argument("--type", help="Media type (movie/tv)", default="movie")
    args = parser.parse_args()

    decoder = VixSrcDecoder()
    result = decoder.get_stream_url(args.id, args.type)

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    else:
        print(f"[*] Extracted HLS URL:")
        print(result['url'])
