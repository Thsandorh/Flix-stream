import unittest

from app import parse_stream_id


class TestTmdbMapping(unittest.TestCase):
    def test_parse_stream_id_supports_urlencoded_imdb_episode(self):
        content_id, season, episode = parse_stream_id("series", "tt27497448%3A1%3A1")
        self.assertEqual((content_id, season, episode), ("tt27497448", "1", "1"))

    def test_parse_stream_id_supports_double_urlencoded_imdb_episode(self):
        content_id, season, episode = parse_stream_id("series", "tt27497448%253A1%253A1")
        self.assertEqual((content_id, season, episode), ("tt27497448", "1", "1"))

    def test_parse_stream_id_rejects_non_imdb(self):
        content_id, season, episode = parse_stream_id("series", "tmdb:224372:1:1")
        self.assertEqual((content_id, season, episode), (None, None, None))


if __name__ == "__main__":
    unittest.main()
