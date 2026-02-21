import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestCineby(unittest.TestCase):
    def test_key_generation(self):
        # We want to test CinebyProvider.generate_key
        # It depends on CinebyProvider class.
        # We can import it inside the test, but we need to ensure dependencies are present.
        # Since we installed dependencies in the env, we don't STRICTLY need to mock them for THIS test
        # unless we want to avoid network calls (which generate_key doesn't do).
        # But cineby_integration imports requests etc. at top level.

        # If we run in an env with dependencies installed, we can just import it.
        # If we want to mock requests to avoid import errors (if not installed), we assume installed.

        # The previous failure was due to global sys.modules hacking breaking other tests.
        # Since we installed 'requests' and 'pycryptodome', we can remove the global mocking
        # and rely on installed packages.

        from cineby_integration import CinebyProvider

        imdb_id = "tt10039344"
        expected_key = "2b2b6e6f6f6c666c6b6b3b6b67693e3a6e3c3a69393b3d3a696c3d696f3d3b6e686f6b6a6b6e393c396f"

        generated = CinebyProvider.generate_key(imdb_id)
        self.assertEqual(generated, expected_key)

if __name__ == '__main__':
    unittest.main()
