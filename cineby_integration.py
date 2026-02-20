import requests
import hashlib
import base64
import json
import logging
import ctypes
import os
import random
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

try:
    from wasmtime import Store, Module, Instance, Func, FuncType, ValType
    WASM_AVAILABLE = True
except ImportError:
    WASM_AVAILABLE = False

logger = logging.getLogger(__name__)

class CinebyProvider:
    BASE_URL = "https://api.videasy.net"
    SALT = "d486ae1ce6fdbe63b60bd1704541fcf0"
    XOR_KEY_SUM = 95 

    @staticmethod
    def generate_key(imdb_id):
        input_str = str(imdb_id) + CinebyProvider.SALT
        res_str = ""
        for c in input_str:
            val = ord(c) ^ CinebyProvider.XOR_KEY_SUM
            res_str += "{:02x}".format(val)
        return res_str

    @staticmethod
    def get_streams(imdb_id, tmdb_id, season=None, episode=None):
        providers = ["moviebox", "hdmovie", "myflixerzupcloud"] 
        
        streams = []
        key = CinebyProvider.generate_key(imdb_id)
        
        media_type = "tv" if season and episode else "movie"
        
        params = {
            "title": "",
            "mediaType": media_type,
            "tmdbId": str(tmdb_id),
            "imdbId": str(imdb_id),
            "key": key,
        }
        
        if media_type == "tv":
            params["seasonId"] = str(season)
            params["episodeId"] = str(episode)
        else:
            params["seasonId"] = "1"
            params["episodeId"] = "1"
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.cineby.gd/",
            "Origin": "https://www.cineby.gd"
        }

        for provider in providers:
            url = f"{CinebyProvider.BASE_URL}/{provider}/sources-with-title"
            try:
                r = requests.get(url, params=params, headers=headers, timeout=10)
                r.raise_for_status()
                response_text = (r.text or "").strip()
                if not response_text:
                    continue

                if response_text.startswith("{") and response_text.endswith("}"):
                    payload = json.loads(response_text)
                    response_text = payload.get("data") or payload.get("result") or ""
                elif response_text.startswith("\"") and response_text.endswith("\""):
                    response_text = json.loads(response_text)
                
                decrypted = CinebyProvider.decrypt_response(response_text, key, tmdb_id)
                if decrypted:
                    data = json.loads(decrypted)
                    sources = data.get("sources")
                    if not isinstance(sources, list):
                        sources = (data.get("data") or {}).get("sources", [])

                    for source in sources:
                        stream_url = source.get("url") or source.get("file") or source.get("src") or source.get("link")
                        if not stream_url:
                            continue
                        quality = source.get("quality") or source.get("label") or "Unknown"
                        source_headers = source.get("headers") if isinstance(source.get("headers"), dict) else {}
                        proxy_headers = dict(headers)
                        proxy_headers.update(source_headers)

                        streams.append({
                            "name": f"Cineby - {provider} - {quality}",
                            "title": f"Cineby {quality}",
                            "url": stream_url,
                            "behaviorHints": {
                                "notWebReady": True,
                                "proxyHeaders": {
                                    "request": proxy_headers
                                }
                            }
                        })
            except Exception as e:
                logger.error(f"Cineby fetch failed for {provider}: {e}")
                
        return streams

    @staticmethod
    def decrypt_response(hex_response, key, tmdb_id):
        if not WASM_AVAILABLE:
            logger.error("WASM runtime (wasmtime) not available.")
            return None

        try:
            wasm_output = CinebyProvider.run_wasm_decrypt(hex_response, tmdb_id)
            if not wasm_output:
                logger.error("WASM decryption returned empty.")
                return None
            
            return CinebyProvider.aes_decrypt(wasm_output, key)
            
        except Exception as e:
            logger.error(f"Cineby decryption failed: {e}")
            return None

    @staticmethod
    def run_wasm_decrypt(input_str, tmdb_id):
        try:
            store = Store()
            module_path = os.path.join(os.path.dirname(__file__), "module.wasm")
            if not os.path.exists(module_path):
                module_path = "module.wasm"
                
            module = Module.from_file(store.engine, module_path)
            
            # Imports
            def seed():
                return random.random()
            
            def abort(a, b, c, d):
                raise RuntimeError(f"WASM abort: {a} {b} {c} {d}")
            
            seed_func = Func(store, FuncType([], [ValType.f64()]), seed)
            abort_func = Func(store, FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], []), abort)
            
            instance = Instance(store, module, [seed_func, abort_func])
            exports = instance.exports(store)
            
            memory = exports["memory"]
            new_func = exports["__new"]
            decrypt_func = exports["decrypt"]
            
            length = len(input_str)
            ptr = new_func(store, length * 2, 2) 
            
            mem_ptr = memory.data_ptr(store)
            mem_size = memory.data_len(store)
            raw_mem = (ctypes.c_ubyte * mem_size).from_address(ctypes.addressof(mem_ptr.contents))
            
            for i, c in enumerate(input_str):
                code = ord(c)
                offset = ptr + (i * 2)
                raw_mem[offset] = code & 0xFF
                raw_mem[offset+1] = (code >> 8) & 0xFF
            
            # Note: tmdb_id is expected as f64 (float) by the WASM signature we inspected indirectly
            # But earlier inspection showed `decrypt` takes (i32, f64) -> i32 based on error message.
            res_ptr = decrypt_func(store, ptr, float(tmdb_id))
            
            if res_ptr == 0:
                return None
            
            header_offset = res_ptr - 4
            b0 = raw_mem[header_offset]
            b1 = raw_mem[header_offset+1]
            b2 = raw_mem[header_offset+2]
            b3 = raw_mem[header_offset+3]
            byte_len = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
            
            char_len = byte_len // 2
            out_str = ""
            for i in range(char_len):
                offset = res_ptr + (i * 2)
                code = raw_mem[offset] | (raw_mem[offset+1] << 8)
                out_str += chr(code)
                
            return out_str
            
        except Exception as e:
            logger.error(f"WASM execution error: {e}")
            return None

    @staticmethod
    def aes_decrypt(ciphertext_b64, passphrase):
        try:
            try:
                data = base64.b64decode(ciphertext_b64)
            except:
                return None

            if data.startswith(b"Salted__"):
                salt = data[8:16]
                ciphertext = data[16:]
                key, iv = CinebyProvider.derive_key_and_iv(passphrase, salt)
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
                return decrypted.decode('utf-8')
            else:
                return None
        except Exception as e:
            logger.error(f"AES decryption failed: {e}")
            return None

    @staticmethod
    def derive_key_and_iv(passphrase, salt):
        d = d_i = b""
        while len(d) < 32 + 16:
            d_i = hashlib.md5(d_i + passphrase.encode() + salt).digest()
            d += d_i
        return d[:32], d[32:48]
