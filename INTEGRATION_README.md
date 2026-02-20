# Integration Guide for Aniways Stream Provider

This document outlines how to integrate the newly implemented stream extraction logic for Aniways into the main `app.py` or another service.

## Prerequisites

All integrations require the following Python packages:
- `requests`
- `base64` (standard library)
- `json` (standard library)

Ensure your `requirements.txt` includes:
```text
requests
```

---

## Aniways (Anime)

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
4. **Header Extraction:**
   - The API response often includes a `proxyHls` field (Base64 encoded JSON).
   - You **must** decode this field to extract the `Referer` and `Origin` headers required to play the stream.
   - Use the `extract_headers_from_proxy` function provided in the blueprint.

### Functionality
The `aniways_integration.py` script demonstrates:
- Fetching episodes for a given Anime ID.
- Finding servers for an episode.
- Extracting the final stream URL and necessary headers.
