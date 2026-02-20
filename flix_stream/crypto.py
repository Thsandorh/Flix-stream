import base64
import hashlib
import json
import logging
import time

import requests
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad

from flix_stream.config import COMMON_HEADERS, MASTER_KEY


logger = logging.getLogger(__name__)

# Simple cache for decryption key.
_KEY_CACHE = {"key": None, "timestamp": 0}


def get_decryption_key():
    """Fetches and decrypts the current VidZee API key with caching (1 hour)."""
    now = time.time()
    if _KEY_CACHE["key"] and (now - _KEY_CACHE["timestamp"] < 3600):
        return _KEY_CACHE["key"]

    try:
        response = requests.get("https://core.vidzee.wtf/api-key", headers=COMMON_HEADERS, timeout=10)
        response.raise_for_status()
        encrypted_data = base64.b64decode(response.text.strip())

        if len(encrypted_data) <= 28:
            return None

        iv = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        key = hashlib.sha256(MASTER_KEY.encode()).digest()
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted_key = cipher.decrypt_and_verify(ciphertext, tag).decode()

        _KEY_CACHE["key"] = decrypted_key
        _KEY_CACHE["timestamp"] = now
        return decrypted_key
    except Exception as exc:
        logger.error("Failed to get decryption key: %s", exc)
        return None


def decrypt_link(encrypted_link, key_str):
    """Decrypts a VidZee server link using AES-CBC."""
    try:
        decoded = base64.b64decode(encrypted_link).decode()
        if ":" not in decoded:
            return None

        iv_b64, cipher_b64 = decoded.split(":")
        iv = base64.b64decode(iv_b64)
        ciphertext = base64.b64decode(cipher_b64)

        key = key_str.encode().ljust(32, b"\0")
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decrypted = cipher.decrypt(ciphertext)

        padding_len = decrypted[-1]
        if padding_len > 16:  # Sanity check for padding.
            return None

        return decrypted[:-padding_len].decode()
    except Exception:
        return None


def decrypt_autoembed_response(data_json):
    """Decrypt AutoEmbed API response using PBKDF2 and AES-CBC."""
    try:
        payload = data_json
        if isinstance(payload, dict) and "data" in payload:
            inner_json_str = base64.b64decode(payload["data"]).decode("utf-8")
            payload = json.loads(inner_json_str)

        key_hex = payload.get("key")
        iv_hex = payload.get("iv")
        salt_hex = payload.get("salt")
        iterations = int(payload.get("iterations", 0))
        encrypted_data_b64 = payload.get("encryptedData")

        if not all([key_hex, iv_hex, salt_hex, encrypted_data_b64]) or iterations <= 0:
            return None

        salt = bytes.fromhex(salt_hex)
        iv = bytes.fromhex(iv_hex)
        encrypted_data = base64.b64decode(encrypted_data_b64)
        key = PBKDF2(key_hex, salt, dkLen=32, count=iterations, hmac_hash_module=SHA256)

        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
        return json.loads(decrypted_data.decode("utf-8"))
    except Exception as exc:
        logger.error("AutoEmbed response decryption failed: %s", exc)
        return None
