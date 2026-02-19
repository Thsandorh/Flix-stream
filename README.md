# FlickyStream Stremio Addon

Ez egy Stremio addon, amely a FlickyStream (VidZee) API-ját használja a videó streamek kinyeréséhez.

## Funkciók
- Automatikus IMDB -> TMDB azonosító leképezés.
- VidZee API kulcsok automatikus lekérése és feloldása.
- Párhuzamos lekérdezés több szerverről (Duke, Glory, Nflix, stb.).

## Telepítés
1. Telepítsd a függőségeket:
   ```bash
   npm install
   ```
2. Állítsd be a TMDB API kulcsodat:
   ```bash
   export TMDB_TOKEN="a_te_tmdb_tokened"
   ```
3. Indítsd el a szervert:
   ```bash
   node index.js
   ```

## Használat Stremio-ban
Add hozzá a következő URL-t az Addons menüben:
`http://localhost:7000/manifest.json`
