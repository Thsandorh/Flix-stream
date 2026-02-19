# VidZee API Reverse Engineering Jelentés

## 1. API Végpont és Paraméterek
A videólejátszó a következő végpontot használja az adatok lekéréséhez:
`https://player.vidzee.wtf/api/server`

**Paraméterek:**
- `id`: TMDB azonosító.
- `sr`: Szerver azonosító (pl. 1 = Duke, 2 = Glory).
- `ss`: Évad száma.
- `ep`: Epizód száma.

## 2. Kulcskezelési Mechanizmus
A rendszer kétlépcsős AES titkosítást alkalmaz.

### 2.1. Első szint: API Kulcs feloldása
`https://core.vidzee.wtf/api-key` -> Titkosított Base64 karakterlánc.
- **Algoritmus:** AES-256-GCM
- **Master Key:** `b3f2a9d4c6e1f8a7b`
- **Kulcs származtatás:** Master Key SHA-256 hash-e.

### 2.2. Második szint: Videó URL feloldása
- **Algoritmus:** AES-256-CBC
- **Kulcs:** A feloldott API kulcs 32 bájtra kiegészítve.

## 3. Node.js Megvalósítás
A projekt az `index.js` és `utils.js` fájlokból áll.

**Telepítés és futtatás:**
```bash
npm install
export TMDB_TOKEN="YOUR_TMDB_TOKEN_HERE"
node index.js
```

Az addon a `http://localhost:7000/manifest.json` címen érhető el Stremio számára.

## 4. Teszt Eredmények
- **Film (Greenland 2):** Sikeresen kinyert 6 stream opció.
- **Válaszidő:** ~1.5 - 2 másodperc.
