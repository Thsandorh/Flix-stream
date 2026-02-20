# Cineby / Videasy Integration Implementation Plan for AI Agents

This document outlines the technical details and steps required to integrate `cineby.gd` (powered by `api.videasy.net`) into a Python-based Stremio addon.

## 1. Overview

Cineby uses a complex protection mechanism involving:
1.  **Request Key Generation:** XOR-based hashing of the IMDb ID + Salt.
2.  **Response Encryption:** The API returns a hex-encoded string which is first processed by a WebAssembly (WASM) module and then decrypted using AES-CBC (OpenSSL KDF).

## 2. Dependencies

The following Python libraries are required:
*   `requests`: For HTTP API calls.
*   `pycryptodome`: For AES decryption.
*   `wasmtime`: For executing the WASM module (`module.wasm`).

## 3. Key Generation Logic

The API requires a hashed key (often used in requests or decryption context).
*   **Salt:** `d486ae1ce6fdbe63b60bd1704541fcf0`
*   **XOR Key:** `8c465aa8af6cbfd4c1f91bf0c8d678ba` (XOR sum = 95)

**Python Implementation:**
```python
def generate_key(imdb_id):
    salt = "d486ae1ce6fdbe63b60bd1704541fcf0"
    xor_sum = 95
    input_str = str(imdb_id) + salt
    res_str = ""
    for c in input_str:
        val = ord(c) ^ xor_sum
        res_str += "{:02x}".format(val)
    return res_str
```

## 4. API Endpoints

**Base URL:** `https://api.videasy.net`

**Endpoint:** `/{provider}/sources-with-title`
*   **Providers:** `moviebox`, `hdmovie`, `myflixerzupcloud`
*   **Method:** GET
*   **Headers:**
    *   `Referer`: `https://www.cineby.gd/`
    *   `Origin`: `https://www.cineby.gd`
*   **Parameters:**
    *   `title`: (Can be empty)
    *   `mediaType`: `movie` or `tv`
    *   `tmdbId`: The TMDB ID
    *   `imdbId`: The IMDb ID
    *   `seasonId`: Season number (for TV) or `1` (Movie)
    *   `episodeId`: Episode number (for TV) or `1` (Movie)

## 5. WASM Integration (Crucial)

The API response is a hex string. This string must be passed to the `decrypt` function exported by `module.wasm`.

**WASM Imports Required:**
The `module.wasm` expects an environment with:
*   `env.seed`: `() -> f64` (Returns a random float)
*   `env.abort`: `(i32, i32, i32, i32) -> void` (Handles abort/errors)

**Execution Flow:**
1.  Load `module.wasm` using `wasmtime`.
2.  Allocate memory for the input string using `__new(size, classId=2)`. Note: String size is `len * 2` (UTF-16).
3.  Write the input hex string to the allocated memory pointer (as UTF-16LE).
4.  Call the exported `decrypt(ptr, tmdb_id)` function.
    *   **Important:** `tmdb_id` must be passed as a float (`f64`).
5.  Read the result from the returned pointer.
    *   The length (in bytes) is stored at `ptr - 4` (4 bytes, little-endian).
    *   Read the string data from `ptr`.

## 6. AES Decryption

The output from the WASM module is a Base64 encoded string (OpenSSL format).

**Algorithm:** AES-CBC
**Key Derivation:** OpenSSL KDF (MD5)
**Passphrase:** The generated key from Step 3.

**Decryption Steps:**
1.  Decode Base64.
2.  Extract Salt (`bytes[8:16]`) if header is `Salted__`.
3.  Derive Key (32 bytes) and IV (16 bytes) using MD5 of `passphrase + salt`.
4.  Decrypt using AES-CBC.
5.  Unpad (PKCS7).
6.  Parse the resulting JSON.

## 7. Example Provider Class

See `cineby_integration.py` in the repository for the full reference implementation incorporating `wasmtime` and `pycryptodome`.
