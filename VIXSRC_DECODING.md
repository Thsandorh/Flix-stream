# VixSrc.to API Extraction Report

## Summary
The `vixsrc.to` streaming link can be extracted **statically** without browser emulation (Playwright/Selenium) or solving complex ROT14 ciphers. The site serves the master playlist configuration directly in the HTML source, alongside a heavy obfuscated ad-network script which acts as a decoy/gatekeeper for browser clients but is not strictly required to construct the stream URL.

## Extraction Logic
1.  **Fetch the Embed Page:** request `https://vixsrc.to/movie/{tmdb_id}` (or `tv/{id}/{s}/{e}`).
2.  **Parse `window.masterPlaylist`:** Locate the JSON object literal assigned to `window.masterPlaylist` in the HTML.
3.  **Construct URL:**
    *   Base URL: `window.masterPlaylist.url` (e.g., `https://vixsrc.to/playlist/{internal_id}`)
    *   Parameters: Append all keys from `window.masterPlaylist.params`.
    *   **Crucial Extra Parameters:** Append `h=1` and `lang=en`.

## Python Implementation
The provided `vixsrc_integration.py` script demonstrates this logic.

```bash
python3 vixsrc_integration.py [TMDB_ID] --type [movie|tv]
```

## "H" Parameter
The user's hint "H kiszedheto" refers to the `h=1` query parameter which is mandatory for the playlist URL to resolve correctly. It is appended dynamically by the `vixsrc-nxIkFVjF.js` script but can be statically added.

## Limitations
*   The extraction relies on the current page structure where `window.masterPlaylist` is exposed in the HTML.
*   The `token` and `expires` parameters are generated server-side and included in the HTML, so a fresh request to the embed page is always required to get a valid link.
