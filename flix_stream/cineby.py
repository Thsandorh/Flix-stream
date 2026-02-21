import base64
import hashlib
import json
import logging
import os
import random
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

try:
    from wasmtime import Store, Module, Instance, Func, FuncType, ValType, Engine
    WASM_AVAILABLE = True
except ImportError:
    WASM_AVAILABLE = False

from flix_stream.config import COMMON_HEADERS
from flix_stream.cache import ttl_cache

logger = logging.getLogger(__name__)

class CinebyProvider:
    BASE_URL = "https://api.videasy.net"
    # Pre-calculated hash for WASM seed 0.5
    # This allows deterministic verification in pure Python without executing obfuscated JS.
    FIXED_WASM_HASH = "b0f54e79a4ed19ca47430e37ff3bd6a03316fd378fb652868927b970ecadefed57f20a9a556e8e7e9a825c9cd633aeab0311f6443417d3470b898b558d6b27aa"

    _wasm_engine = None
    _wasm_module = None

    @classmethod
    def _get_wasm(cls):
        if not WASM_AVAILABLE:
            return None, None
        if cls._wasm_engine is None:
            try:
                cls._wasm_engine = Engine()
                module_path = os.path.join(os.path.dirname(__file__), "module.wasm")
                if not os.path.exists(module_path):
                    # Fallback for local testing
                    module_path = "module.wasm"
                if os.path.exists(module_path):
                    cls._wasm_module = Module.from_file(cls._wasm_engine, module_path)
                else:
                    logger.error("module.wasm not found at %s", module_path)
            except Exception as e:
                logger.error("Failed to load WASM engine: %s", e)
        return cls._wasm_engine, cls._wasm_module

    @staticmethod
    def derive_key_and_iv(passphrase, salt):
        """OpenSSL compatible key derivation (MD5 KDF)."""
        d = d_i = b""
        while len(d) < 32 + 16:
            d_i = hashlib.md5(d_i + passphrase.encode() + salt).digest()
            d += d_i
        return d[:32], d[32:48]

    @staticmethod
    def aes_decrypt(ciphertext_b64, passphrase=""):
        """Decrypt OpenSSL-formatted AES-CBC ciphertext."""
        try:
            data = base64.b64decode(ciphertext_b64)
            if data.startswith(b"Salted__"):
                salt = data[8:16]
                ciphertext = data[16:]
                key, iv = CinebyProvider.derive_key_and_iv(passphrase, salt)
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
                return decrypted.decode('utf-8')
        except Exception as e:
            logger.debug("AES decryption failed: %s", e)
        return None

    @staticmethod
    @ttl_cache(ttl_seconds=3600)
    def fetch_streams(tmdb_id, imdb_id=None, media_type="movie", season=1, episode=1):
        engine, module = CinebyProvider._get_wasm()
        if not module:
            logger.error("Cineby provider unavailable: WASM module not loaded.")
            return []

        providers = ["moviebox", "hdmovie", "myflixerzupcloud"]
        headers = COMMON_HEADERS.copy()
        headers.update({
            "Referer": "https://www.cineby.gd/",
            "Origin": "https://www.cineby.gd"
        })

        streams = []
        for provider in providers:
            url = f"{CinebyProvider.BASE_URL}/{provider}/sources-with-title"
            params = {
                "tmdbId": str(tmdb_id),
                "imdbId": str(imdb_id or ""),
                "mediaType": media_type,
                "seasonId": str(season),
                "episodeId": str(episode),
                "title": ""
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=10)
                if r.status_code != 200 or r.text.startswith("{") or len(r.text) < 100:
                    continue

                # Step 1: WASM Decrypt
                b64_ciphertext = CinebyProvider._run_wasm_decrypt(engine, module, r.text, tmdb_id)
                if not b64_ciphertext:
                    continue

                # Step 2: AES Decrypt (passphrase is empty string based on reverse engineering)
                final_json_str = CinebyProvider.aes_decrypt(b64_ciphertext, "")
                if final_json_str:
                    data = json.loads(final_json_str)
                    for source in data.get("sources", []):
                        streams.append({
                            "name": f"Cineby - {provider}",
                            "title": f"Cineby {source.get('quality', 'HD')}",
                            "url": source.get("url"),
                            "behaviorHints": {
                                "notWebReady": True,
                                "proxyHeaders": {"request": headers}
                            }
                        })
            except Exception as e:
                logger.error("Error fetching from Cineby provider %s: %s", provider, e)

        return streams

    @staticmethod
    def _run_wasm_decrypt(engine, module, hex_response, tmdb_id):
        try:
            store = Store(engine)
            # Use deterministic seed to match our FIXED_WASM_HASH
            seed_func = Func(store, FuncType([], [ValType.f64()]), lambda: 0.5)
            abort_func = Func(store, FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], []), lambda a,b,c,d: None)

            instance = Instance(store, module, [seed_func, abort_func])
            exports = instance.exports(store)

            memory = exports["memory"]
            new_func = exports["__new"]
            verify_func = exports["verify"]
            decrypt_func = exports["decrypt"]

            def write_str(s):
                b = s.encode("utf-16-le")
                ptr = new_func(store, len(b), 2)
                memory.write(store, b, ptr)
                return ptr

            def read_str(ptr):
                if not ptr: return None
                byte_len = int.from_bytes(memory.read(store, ptr - 4, ptr), "little")
                return memory.read(store, ptr, ptr + byte_len).decode("utf-16-le")

            # Initialize/Verify WASM
            verify_func(store, write_str(CinebyProvider.FIXED_WASM_HASH))

            # Decrypt response
            res_ptr = decrypt_func(store, write_str(hex_response), float(tmdb_id))
            return read_str(res_ptr)
        except Exception as e:
            logger.error("WASM decryption failed: %s", e)
            return None
