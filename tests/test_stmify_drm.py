import unittest
import sys
import os
import json
from unittest.mock import MagicMock

# Mock requests before importing integration
sys.modules["requests"] = MagicMock()

# Add parent directory to path to import stmify_integration
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to mock Flask app context for url_root
from flask import Flask
app = Flask(__name__)

from stmify_integration import get_stmify_catalog_static, get_stmify_stream, proxy_mpd, license_server

class TestStmify(unittest.TestCase):
    def test_catalog_static(self):
        print("Testing Static Catalog...")
        metas = get_stmify_catalog_static(skip=0)
        self.assertGreater(len(metas), 0)
        print(f"Loaded {len(metas)} items.")

    def test_stream_drm(self):
        print("Testing DRM Stream Resolution...")
        test_channels = [{
            "slug": "test-drm",
            "name": "Test DRM Channel",
            "stream_url": "https://example.com/manifest.mpd",
            "k1": "deadbeef",
            "k2": "feedface"
        }]

        import stmify_integration
        original_load = stmify_integration.load_channels
        stmify_integration.load_channels = lambda: test_channels

        with app.test_request_context('/'):
            streams = get_stmify_stream("stmify:test-drm")
            self.assertEqual(len(streams), 1)
            print(f"Stream URL: {streams[0]['url']}")
            self.assertIn("/stmify/proxy/test-drm.mpd", streams[0]['url'])

        stmify_integration.load_channels = original_load

    def test_license_server(self):
        print("Testing License Server...")
        test_channels = [{
            "slug": "test-drm",
            "k1": "00112233445566778899aabbccddeeff", # 16 bytes hex
            "k2": "ffeeddccbbaa99887766554433221100"
        }]

        import stmify_integration
        original_load = stmify_integration.load_channels
        stmify_integration.load_channels = lambda: test_channels

        with app.test_request_context():
            resp = license_server("test-drm")
            data = resp.json
            print(f"License Response: {data}")
            self.assertIn("keys", data)
            # Correct expectation derived from actual run
            self.assertEqual(data["keys"][0]["kid"], "ABEiM0RVZneImaq7zN3u_w")
            self.assertEqual(data["keys"][0]["k"], "_-7dzLuqmYh3ZlVEMyIRAA")

        stmify_integration.load_channels = original_load

if __name__ == '__main__':
    unittest.main()
