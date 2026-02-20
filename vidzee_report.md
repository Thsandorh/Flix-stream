# FlickyStream / VidZee API & Stremio Addon Jelentés

## 1. API és Titkosítási Összegzés
A FlickyStream (flickystream.ru) a VidZee lejátszót használja, amely kétlépcsős AES titkosítással védi a videó linkeket.

- **Végpontok:**
  - Keresés: TMDB API (`api.themoviedb.org`)
  - Kulcs: `https://core.vidzee.wtf/api-key`
  - Stream: `https://player.vidzee.wtf/api/server`
  - Letöltés: `https://dl.vidzee.wtf/download/`

- **Kulcsok:**
  - Master Key: `b3f2a9d4c6e1f8a7b`
  - Feloldott kulcs (példa): `ifyouscrapeyouaregay`

## 2. Stremio Addon Megvalósítás
Az elkészült Stremio addon (`app.py`) automatikusan elvégzi a következő lépéseket:
1. IMDB ID leképezése TMDB ID-ra.
2. Aktuális dekódoló kulcs lekérése és feloldása.
3. VidZee szerverek (Duke, Glory, Nflix, stb.) párhuzamos lekérdezése.
4. Titkosított linkek feloldása és visszaadása a Stremionak.

## 3. Telepítés és Futtatás
Szükséges csomagok: `flask`, `requests`, `pycryptodome`.

```bash
pip install flask requests pycryptodome
python app.py
```

Az addon a `http://localhost:7000/manifest.json` címen érhető el, amit Stremio-ba importálva azonnal használható.

## 4. Teszt Eredmények
- **Film (Greenland 2):** 6 stream talált.
- **Sorozat (GoT S01E01):** 3 stream talált.
- **Válaszidő:** ~1.8 másodperc a párhuzamos feldolgozásnak köszönhetően.
