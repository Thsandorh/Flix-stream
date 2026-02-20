import requests
import re
import json
import sys

class VixSrcDecoder:
    """
    Decodes the obfuscated API/Player configuration from vixsrc.to.
    The site uses a ROT14 cipher on client-side JavaScript strings.
    """

    BASE_URL = "https://vixsrc.to"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    @staticmethod
    def rot14(s):
        """Decodes a string using the ROT14 cipher (Shift +14)."""
        if not isinstance(s, str):
            return s
        result = []
        for char in s:
            if 'a' <= char <= 'z':
                result.append(chr((ord(char) - 97 + 14) % 26 + 97))
            elif 'A' <= char <= 'Z':
                result.append(chr((ord(char) - 65 + 14) % 26 + 65))
            else:
                result.append(char)
        return "".join(result)

    def get_decoded_config(self, tmdb_id, media_type="movie"):
        """Fetches and decodes the configuration."""
        url = f"{self.BASE_URL}/{media_type}/{tmdb_id}"
        headers = {"User-Agent": self.USER_AGENT, "Referer": self.BASE_URL}

        print(f"[*] Fetching {url}...", file=sys.stderr)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            return {"error": f"Failed to fetch page: {e}"}

        # Find signature "AzOxuow" (x: OnClick)
        signature = "AzOxuow"
        idx = html.find(signature)
        if idx == -1:
             if "Just a moment..." in html:
                 return {"error": "Cloudflare Challenge Detected. Browser required."}
             return {"error": "Could not find configuration signature in HTML."}

        # Walk back to find the start of the object
        # It's usually passed to entries({...})
        start_idx = html.rfind("entries({", 0, idx)
        if start_idx == -1:
             start_idx = html.rfind("({", 0, idx)

        if start_idx == -1:
            return {"error": "Could not find start of config object."}

        open_brace = html.find("{", start_idx)

        # Find matching closing brace
        cnt = 0
        end_idx = -1
        for i in range(open_brace, len(html)):
            if html[i] == '{': cnt += 1
            elif html[i] == '}':
                cnt -= 1
                if cnt == 0:
                    end_idx = i + 1
                    break

        if end_idx == -1:
            return {"error": "Could not parse object boundaries."}

        raw_json_like = html[open_brace:end_idx]
        decoded_data = {}

        # Regex to extract key-value pairs
        # Improved regex to handle quoted keys and empty strings correctly
        # Matches: key:"val", "key":"val", key:123
        pairs = re.findall(r'(?:["\']?([a-zA-Z0-9_]+)["\']?)\s*:\s*(?:"([^"]*)"|\'([^\']*)\'|([0-9\.]+)|(null|true|false))', raw_json_like)

        if not pairs:
             return {"error": "Found config object but failed to parse keys."}

        for key, val_d, val_s, val_n, val_l in pairs:
            if val_d is not None and val_d != "":
                decoded_data[key] = self.rot14(val_d)
            elif val_s is not None and val_s != "":
                decoded_data[key] = self.rot14(val_s)
            elif val_d == "" or val_s == "": # Handle empty strings explicitly
                decoded_data[key] = ""
            elif val_n:
                decoded_data[key] = float(val_n) if '.' in val_n else int(val_n)
            elif val_l:
                decoded_data[key] = val_l

        return decoded_data

    def analyze_config(self, config):
        """Analyzes the decoded configuration for next steps."""
        analysis = {}

        # Ad Network / Verification URL
        if "Kj" in config and "l" in config and "WK" in config:
            zone_id = config["l"]
            params = config["WK"]
            base_ad_url = config["Kj"]
            if base_ad_url.startswith("//"):
                base_ad_url = "https:" + base_ad_url

            analysis["ad_verification_url"] = f"{base_ad_url}{zone_id}{params}"

        # Delivery Method
        if "pK" in config:
            analysis["delivery_method"] = config["pK"] # requestByCSS

        if "vM" in config and "QM" in config:
            analysis["tag_url_template"] = f"{config['vM']}[random_domain]{config['QM']}"

        return analysis

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Decode VixSrc API Config")
    parser.add_argument("id", nargs='?', help="TMDB ID of the movie", default="27205")
    args = parser.parse_args()

    decoder = VixSrcDecoder()
    config = decoder.get_decoded_config(args.id)

    if "error" in config:
        print(f"Error: {config['error']}")
        sys.exit(1)

    print(f"[*] Successfully decoded configuration for ID {args.id}")

    analysis = decoder.analyze_config(config)
    print("\n--- Analysis ---")
    for k, v in analysis.items():
        print(f"{k}: {v}")

    print("\n--- Next Steps ---")
    print("1. The 'ad_verification_url' is likely the gatekeeper.")
    print("2. The script generates a random domain and fetches 'tag.min.js'.")
    print("3. Browser emulation is required to execute the ad script and bypass the sandbox check.")

    # Dump full config
    with open("vixsrc_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n[*] Full configuration saved to 'vixsrc_config.json'")
