# VidZee API Reverse Engineering Jelentés

## 1. API Végpont és Paraméterek
A videólejátszó a következő végpontot használja az adatok lekéréséhez:
`https://player.vidzee.wtf/api/server`

**Paraméterek:**
- `id`: TMDB (The Movie Database) azonosító.
- `sr`: Szerver azonosító (pl. 1 = Duke, 2 = Glory).
- `ss`: Évad száma (sorozatok esetén).
- `ep`: Epizód száma (sorozatok esetén).

## 2. Kulcskezelési Mechanizmus
A rendszer kétlépcsős AES titkosítást alkalmaz.

### 2.1. Első szint: API Kulcs feloldása
A lejátszó betöltésekor egy GET kérést indít a `https://core.vidzee.wtf/api-key` címre. Ez egy titkosított Base64 karakterláncot ad vissza.

**Dekódolási folyamat:**
- **Algoritmus:** AES-256-GCM
- **Master Key:** `b3f2a9d4c6e1f8a7b` (a JavaScript kódban hardkódolva).
- **Kulcs származtatás:** A Master Key SHA-256 hash-e.
- **Adatfelépítés:**
  - Első 12 bájt: IV (Nonce)
  - Következő 16 bájt: Authentication Tag
  - Maradék: Ciphertext (visszafejtés előtt az utolsó két részt megcserélik a kódban, de a standard GCM implementációk ezt kezelik).

A dekódolt eredmény jelenleg: `ifyouscrapeyouaregay`.

### 2.2. Második szint: Videó URL feloldása
Az API válaszban szereplő `url` listában a `link` mező tartalmazza a titkosított adatot.

**Formátum:** `base64(iv_base64 : ciphertext_base64)`

**Dekódolási folyamat:**
- **Algoritmus:** AES-256-CBC
- **Kulcs:** A 2.1. pontban kapott szöveg, 32 bájtra kiegészítve null (`\0`) karakterekkel.
- **Padding:** PKCS7

## 3. Technikai Megvalósítás (Python)

```python
import base64
import hashlib
from Crypto.Cipher import AES
import requests

def get_decryption_key():
    master_key = "b3f2a9d4c6e1f8a7b"
    response = requests.get("https://core.vidzee.wtf/api-key")
    encrypted_data = base64.b64decode(response.text.strip())

    iv = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]

    key = hashlib.sha256(master_key.encode()).digest()
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    return cipher.decrypt_and_verify(ciphertext, tag).decode()

def decrypt_link(encrypted_link, key_str):
    decoded = base64.b64decode(encrypted_link).decode()
    iv_b64, cipher_b64 = decoded.split(':')

    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(cipher_b64)
    key = key_str.encode().ljust(32, b'\0')

    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    decrypted = cipher.decrypt(ciphertext)
    padding_len = decrypted[-1]
    return decrypted[:-padding_len].decode()

# Példa használat
key = get_decryption_key()
link = "amxreWlnbHRkSjA2Rm1IT1BvZFVEZz09Ok4vcWp1Z3Vub3pFWjg0RG1ETGhuVWVjamxnMWpnSVIzcEhodEVGR2hSSXI5SlZlcjlQdjhXUVVVdzdxUXhxR3NkTjRhT1Via0k3R2srOERONjRPTzZRPT0="
video_url = decrypt_link(link, key)
print(f"Decoded Video URL: {video_url}")
```

## 4. Egyéb megfigyelések
- A lejátszó a TMDB API-t is használja metaadatokhoz egy fix Bearer tokennel.
- A hálózati forgalomban érdemes figyelni a `Referer` fejlécre (`https://player.vidzee.wtf/`), mivel egyes szerverek ellenőrizhetik azt.
