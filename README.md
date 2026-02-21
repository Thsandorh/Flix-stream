# Flix-Streams (Stremio Addon)

Flix-Streams is a Flask-based Stremio addon that resolves IMDb IDs to TMDB IDs and returns stream links from multiple upstream providers.

## Support & Community

[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Development-29abe0?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sandortoth)
[![Join Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/GnKRAwwdcQ)

## What It Does

- Supports `movie` and `series`.
- Accepts Stremio IDs with IMDb prefix (`tt...`).
- Converts IMDb -> TMDB before provider API calls.
- Supports tokenized Stremio configuration URLs (`/<configToken>/manifest.json`).
- Fetches streams from:
  - VidZee (`player.vidzee.wtf`)
  - AutoEmbed (`test.autoembed.cc`)
  - VixSrc (`vixsrc.to`)
  - Aniways (`api.aniways.xyz`) with direct Aniways and Kitsu ID support
  - Famelack Live TV (country-based catalogs powered by `famelack/famelack-channels`)
- Merges subtitles from:
  - Upstream provider tracks
  - Wyzie Subs API (`sub.wyzie.ru`) with configurable language/source/format filters

## Current ID Behavior

- Manifest `idPrefixes`: `["tt", "tmdb", "aniways", "kitsu"]` (+ `famelack` when at least one Live TV country is selected)
- Also supports `tmdb:<id>` IDs.
- Famelack input: `famelack:<country_code>:<nanoid>` (for example `famelack:hu:abc123xyz`)
- Live TV catalogs are created per selected country as `famelack-<country_code>` (for example `famelack-hu`).
- Country options are served by `/api/famelack/countries`.
- Movie input: `tt1234567`
- Series input: `tt1234567:season:episode`
- Aniways direct input: `aniways:<anime_id>:<episode>` (or `aniways:<anime_id>:<season>:<episode>`)
- Kitsu input: `kitsu:<kitsu_id>:<episode>` (or `kitsu:<kitsu_id>:<season>:<episode>`)
- Series fallback:
  - If season/episode is missing, it attempts to resolve episode context from TMDB `find` results.

## Run Locally

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Start server:
   - `python app.py`
3. Open configure page:
   - `http://127.0.0.1:7000/configure`
4. Pick provider/Wyzie settings, then install the generated manifest URL into Stremio.

Default port is `7000` (can be changed with `PORT` env var).

## Environment Variables

- `PORT` (optional): HTTP port, default `7000`
- `TMDB_TOKEN` (optional): TMDB bearer token (fallback token is embedded in code)

## Notes

- Upstream providers can change behavior at any time.
- Some HLS links require proxy headers; the addon sets Stremio `behaviorHints` where needed.
- After changing configuration, reinstall addon in Stremio to refresh cache.
