import unittest
import sys
import os
import json

# Add parent directory to path to import stmify_integration
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from stmify_integration import get_stmify_catalog_static, get_stmify_stream

class TestStmify(unittest.TestCase):
    def test_catalog(self):
        print("Testing Stmify Catalog (Static)...")
        # New signature uses skip, not page
        metas = get_stmify_catalog_static(skip=0)
        print(f"Found {len(metas)} items in catalog.")
        if len(metas) > 0:
            print(f"First item: {metas[0]}")
            self.assertTrue(metas[0]["id"].startswith("stmify:"))
            self.assertTrue(metas[0]["type"] == "series")
            self.assertTrue("name" in metas[0])
            # self.assertTrue("poster" in metas[0]) # Poster might be None
        else:
            print("Warning: Catalog returned 0 items. Check JSON.")
            self.fail("Catalog returned 0 items")

    def test_stream_resolution(self):
        print("\nTesting Stmify Stream Resolution (TV1)...")
        # TV1 is a known channel from exploration
        stream_id = "stmify:tv1"
        streams = get_stmify_stream(stream_id)
        print(f"Found {len(streams)} streams.")
        if len(streams) > 0:
            print(f"Stream: {streams[0]}")
            self.assertTrue("url" in streams[0])
            self.assertTrue(streams[0]["url"].startswith("http"))
        else:
            print("Warning: Stream resolution failed for TV1.")
            # Fail if resolution fails for known working channel
            self.fail("Stream resolution failed")

if __name__ == '__main__':
    unittest.main()
