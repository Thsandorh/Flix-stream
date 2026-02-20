import unittest

from app import parse_stream_id


class TestStreamIdParsing(unittest.TestCase):
    def test_supports_imdb_episode(self):
        content_id, season, episode = parse_stream_id("series", "tt1480055:01:01")
        self.assertEqual((content_id, season, episode), ("tt1480055", "01", "01"))

    def test_supports_compact_imdb_sxe(self):
        content_id, season, episode = parse_stream_id("series", "tt1480055:s01e02")
        self.assertEqual((content_id, season, episode), ("tt1480055", "01", "02"))

    def test_supports_urlencoded_imdb_episode(self):
        content_id, season, episode = parse_stream_id("series", "tt27497448%3A1%3A1")
        self.assertEqual((content_id, season, episode), ("tt27497448", "1", "1"))

    def test_supports_double_urlencoded_imdb_episode(self):
        content_id, season, episode = parse_stream_id("series", "tt27497448%253A1%253A1")
        self.assertEqual((content_id, season, episode), ("tt27497448", "1", "1"))

    def test_rejects_non_imdb_id(self):
        content_id, season, episode = parse_stream_id("series", "tmdb:224372:1:1")
        self.assertEqual((content_id, season, episode), (None, None, None))


if __name__ == "__main__":
    unittest.main()
