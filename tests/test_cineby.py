import unittest
import sys
import os
import hashlib
from unittest.mock import MagicMock

# Add the parent directory to sys.path to import modules from the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock dependencies
sys.modules['requests'] = MagicMock()
sys.modules['wasmtime'] = MagicMock()
sys.modules['Crypto'] = MagicMock()
sys.modules['Crypto.Cipher'] = MagicMock()
sys.modules['Crypto.Util.Padding'] = MagicMock()

class TestCineby(unittest.TestCase):
    def test_derive_key_and_iv(self):
        from flix_stream.cineby import CinebyProvider

        passphrase = "test_passphrase"
        salt = b"12345678"

        key, iv = CinebyProvider.derive_key_and_iv(passphrase, salt)

        # Verify manually
        d = d_i = b""
        while len(d) < 48:
            d_i = hashlib.md5(d_i + passphrase.encode() + salt).digest()
            d += d_i

        self.assertEqual(key, d[:32])
        self.assertEqual(iv, d[32:48])

if __name__ == '__main__':
    unittest.main()
