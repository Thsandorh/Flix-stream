# Required Modifications for `app.py`

To fully support Aniways streaming, you need to add the following logic to your main `app.py` file. This logic is responsible for decoding the special headers (`Referer`, `Origin`) required by Aniways streams, which are hidden inside a Base64-encoded field in the API response.

## 1. Add Imports
At the top of `app.py`, ensure you have imported the `json` module. It is required to parse the decoded headers.

```python
import os
import re
import base64
import json  # <--- Add this line
import hashlib
import time
# ... (rest of imports)
```

## 2. Add Helper Function
Add the `extract_headers_from_proxy` function anywhere in `app.py` (e.g., before `get_tmdb_id` or with other utility functions). This function takes the `proxyHls` string from the Aniways API and returns a dictionary with the correct headers.

```python
def extract_headers_from_proxy(proxy_url):
    """
    Extracts Referer and Origin headers from the proxyHls string (Aniways).
    Format is typically: /proxy/hd/{base64_headers}/{base64_url}
    """
    try:
        # Split by '/' and find the segment starting with 'ey' (base64 for JSON '{')
        parts = proxy_url.split('/')
        for part in parts:
            if part.startswith('ey'):
                # Add padding if necessary for base64 decoding
                padding = len(part) % 4
                if padding:
                    part += '=' * (4 - padding)

                decoded_bytes = base64.b64decode(part)
                headers_json = json.loads(decoded_bytes)

                # Normalize keys to title case if needed
                headers = {}
                if "referer" in headers_json:
                    headers["Referer"] = headers_json["referer"]
                if "origin" in headers_json:
                    headers["Origin"] = headers_json["origin"]
                return headers
    except Exception as e:
        app.logger.error(f"Error parsing proxy headers: {e}")
    return {}
```

## Why is this needed?
Aniways streams often return a 403 Forbidden error if you try to play them directly. The `proxyHls` field in their API response contains the specific `Referer` and `Origin` values needed to authorize the request. This function extracts those values so you can pass them to the player (e.g., Stremio) via `proxyHeaders`.
