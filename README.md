# Flix-Streams (Stremio Addon)

Flix-Streams is a Flask-based Stremio addon that resolves IMDb IDs to TMDB IDs and returns stream links from multiple upstream providers.

## What It Does

- Supports `movie` and `series`.
- Accepts Stremio IDs with IMDb prefix (`tt...`).
- Converts IMDb -> TMDB before provider API calls.
- Fetches streams from:
  - VidZee (`player.vidzee.wtf`)
  - AutoEmbed (`test.autoembed.cc`)
  - Cineby / Videasy (`api.videasy.net`)
- Returns subtitles when available.

## Current ID Behavior

- Manifest `idPrefixes`: `["tt"]`
- Movie input: `tt1234567`
- Series input: `tt1234567:season:episode`
- Series fallback:
  - If season/episode is missing, it attempts to resolve episode context from TMDB `find` results.

## Run Locally

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Start server:
   - `python app.py`
3. Open configure page:
   - `http://127.0.0.1:7000/configure`

Default port is `7000` (can be changed with `PORT` env var).

## Environment Variables

- `PORT` (optional): HTTP port, default `7000`
- `TMDB_TOKEN` (optional): TMDB bearer token (fallback token is embedded in code)

## Notes

- Upstream providers can change behavior at any time.
- Some HLS links require proxy headers; the addon sets Stremio `behaviorHints` where needed.
- Cineby decryption requires `module.wasm` and the `wasmtime` dependency.
- After any manifest/version change, remove and reinstall the addon in Stremio to refresh cache.
