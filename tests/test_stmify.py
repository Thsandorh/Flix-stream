import unittest
from unittest.mock import patch

from flix_stream.stmify import get_stmify_catalog, get_stmify_stream


class TestStmify(unittest.TestCase):
    def tearDown(self):
        from flix_stream import stmify

        stmify.load_channels.cache_clear()

    @patch("flix_stream.stmify._load_channels_data")
    def test_get_stmify_catalog_uses_static_data(self, mock_load):
        mock_load.return_value = [
            {"id": "stmify:no-stream", "slug": "no-stream", "name": "No Stream", "poster": "x"},
            {
                "id": "stmify:tv1",
                "slug": "tv1",
                "name": "TV1",
                "poster": "https://img.example/tv1.jpg",
                "stream_url": "https://stream.example/live.m3u8",
            },
        ]

        metas = get_stmify_catalog(skip=0, limit=20)
        self.assertEqual(len(metas), 2)
        self.assertEqual(metas[0]["id"], "stmify:tv1")
        self.assertIn("(Stream Available)", metas[0]["description"])
        self.assertIn("(No Stream)", metas[1]["description"])

    @patch("flix_stream.stmify._load_channels_data")
    def test_get_stmify_stream_resolves_from_static_data(self, mock_load):
        mock_load.return_value = [
            {"id": "stmify:tv1", "slug": "tv1", "name": "TV1", "stream_url": "https://stream.example/live.m3u8"},
        ]
        streams = get_stmify_stream("stmify:tv1")

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["name"], "Stmify")
        self.assertEqual(streams[0]["url"], "https://stream.example/live.m3u8")


if __name__ == "__main__":
    unittest.main()
