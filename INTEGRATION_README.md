# Integration Guide for New Stream Providers

This document outlines how to integrate the newly implemented stream extraction logic into the main `app.py` or another service. Each provider has a standalone blueprint script containing the necessary logic, decryption algorithms, and API patterns.

## Prerequisites

All integrations require the following Python packages:
- `requests`
- `pycryptodome` (for AES-CBC and PBKDF2 decryption)

Ensure your `requirements.txt` includes:
```text
requests
pycryptodome
```

---

## 1. AutoEmbed (Movies & TV)

**Blueprint File:** `autoembed_integration.py`

### Overview
AutoEmbed uses AES-CBC encryption with a key derived via PBKDF2 (HMAC-SHA256). The API response is a JSON object wrapped in Base64.

### Integration Steps
1. **Copy Imports:** Ensure `Crypto.Cipher.AES`, `Crypto.Protocol.KDF.PBKDF2`, `Crypto.Hash.SHA256`, `Crypto.Util.Padding.unpad` are imported.
2. **Copy Helper Function:** Copy `decrypt_response(data_json)` from the blueprint to your main application.
3. **Stream Fetching:**
   - Use the `fetch_server_streams` logic.
   - **Endpoint:** `https://test.autoembed.cc/api/server`
   - **Headers:** `Referer` and `Origin` must be set to `https://test.autoembed.cc` (or the specific embed URL).
   - **Parameters:** `id` (TMDB ID), `sr` (Server ID), `ss` (Season), `ep` (Episode).
4. **Server IDs:** Valid IDs are `2` (Glory), `3` (Server 3), `7` (Server 7), `9` (Hindi).

---

## 2. AutoEmbed (Anime)

**Blueprint File:** `anime_autoembed_integration.py`

### Overview
Similar to the Movie/TV version but uses a different domain and endpoint structure.
*Note: This API is currently protected by Cloudflare (Error 522/Timeout) and may require a proxy or residential IP.*

### Integration Steps
1. **Decryption:** Uses the same `decrypt_response` function as the Movie/TV integration.
2. **URL Structure:**
   - **Embed:** `https://anime.autoembed.cc/embed/{slug}-episode-{num}`
   - **API:** `https://anime.autoembed.cc/api/server`
3. **ID Handling:** You may need to extract the internal ID from the embed page HTML (`data-id` or JS variable `id`) before calling the API.

---

## 3. Aniways (Anime)

**Blueprint File:** `aniways_integration.py`

### Overview
Aniways provides direct m3u8 links via a multi-step API process.

### Integration Steps
1. **Fetch Episodes:** `GET https://api.aniways.xyz/anime/{anime_id}/episodes`
2. **Fetch Servers:** `GET https://api.aniways.xyz/anime/{anime_id}/episodes/{episode_id}/servers`
3. **Fetch Stream:** `GET https://api.aniways.xyz/anime/{anime_id}/episodes/servers/{server_id}`
   - **Crucial:** You must pass the correct query parameters:
     - `server`: The server name converted to lowercase with spaces replaced by dashes (e.g., "HD-1" -> `hd-1`).
     - `type`: The stream type (e.g., `sub`).
   - **Example:** `?server=hd-1&type=sub`

---

## 4. VidSrc (Movies & TV)

**Blueprint File:** `vidsrc_integration.py`

### Overview
VidSrc uses a redirect chain that ends with a Cloudflare Turnstile challenge.
**Important:** Pure server-side requests (Python `requests`) **will fail** at the final step (`prorcp`). You need browser automation (Playwright/Selenium) or a solver service.

### Integration Steps
1. **Domain Resolution:** Iterate through the list of domains in `VIDSRC_DOMAINS` to find a working one.
2. **Hash Extraction:** Scrape the embed page `https://{domain}/embed/{id}` for `data-hash` in `<div class="server">`.
3. **RCP Redirect:** Request `https://cloudnestra.com/rcp/{hash}` with the embed URL as `Referer`.
4. **Final Step (Browser Required):**
   - The RCP response contains a path to `/prorcp/{hash}`.
   - **Action:** Open this URL in a browser/headless browser.
   - **Action:** Solve the Cloudflare Turnstile widget.
   - **Result:** Capture the network traffic or `Playerjs` config to get the final m3u8 URL.
