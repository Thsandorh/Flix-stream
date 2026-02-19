import unittest
from unittest.mock import patch

from app import get_tmdb_id, get_series_context_from_imdb, parse_stream_id


class MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestTmdbMapping(unittest.TestCase):
    def setUp(self):
        get_tmdb_id.cache_clear()
        get_series_context_from_imdb.cache_clear()

    @patch('app.requests.get')
    def test_series_uses_tv_show_id_from_episode_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [],
            'tv_results': [],
            'tv_episode_results': [{'id': 999, 'show_id': 1399}],
        })

        tmdb_id = get_tmdb_id('tt1480055', 'series')

        self.assertEqual(tmdb_id, 1399)

    @patch('app.requests.get')
    def test_series_prefers_tv_result_over_movie_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [{'id': 27205}],
            'tv_results': [{'id': 1399}],
            'tv_episode_results': [],
        })

        tmdb_id = get_tmdb_id('tt0944947', 'series')

        self.assertEqual(tmdb_id, 1399)

    @patch('app.requests.get')
    def test_series_does_not_fallback_to_movie_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [{'id': 27205}],
            'tv_results': [],
            'tv_episode_results': [],
        })

        tmdb_id = get_tmdb_id('tt-any', 'series')

        self.assertIsNone(tmdb_id)

    @patch('app.requests.get')
    def test_tv_alias_is_treated_as_series(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [{'id': 27205}],
            'tv_results': [{'id': 1399}],
            'tv_episode_results': [],
        })

        tmdb_id = get_tmdb_id('tt0944947', 'tv')

        self.assertEqual(tmdb_id, 1399)

    @patch('app.requests.get')
    def test_series_uses_tv_show_id_from_season_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [],
            'tv_results': [],
            'tv_episode_results': [],
            'tv_season_results': [{'id': 1001, 'show_id': 1399}],
        })

        tmdb_id = get_tmdb_id('tt-season', 'series')

        self.assertEqual(tmdb_id, 1399)

    @patch('app.requests.get')
    def test_movie_prefers_movie_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [{'id': 27205}],
            'tv_results': [{'id': 1399}],
            'tv_episode_results': [],
        })

        tmdb_id = get_tmdb_id('tt1375666', 'movie')

        self.assertEqual(tmdb_id, 27205)

    @patch('app.get_tmdb_id')
    def test_parse_stream_id_supports_imdb_episode(self, mock_map):
        mock_map.return_value = 1399

        tmdb_id, season, episode = parse_stream_id('series', 'tt1480055:01:01')

        self.assertEqual((tmdb_id, season, episode), (1399, '01', '01'))

    def test_parse_stream_id_supports_tmdb_direct(self):
        tmdb_id, season, episode = parse_stream_id('series', 'tmdb:224372:1:1')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '1'))

    def test_parse_stream_id_supports_tmdb_typed_variant(self):
        tmdb_id, season, episode = parse_stream_id('series', 'tmdb:tv:224372:1:1')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '1'))

    def test_parse_stream_id_supports_tmdb_series_variant(self):
        tmdb_id, season, episode = parse_stream_id('series', 'tmdb:series:224372:1:1')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '1'))

    def test_parse_stream_id_supports_tmdb_movie_variant(self):
        tmdb_id, season, episode = parse_stream_id('movie', 'tmdb:movie:27205')

        self.assertEqual((tmdb_id, season, episode), (27205, None, None))

    @patch('app.get_tmdb_id')
    def test_parse_stream_id_supports_compact_imdb_sxe(self, mock_map):
        mock_map.return_value = 1399

        tmdb_id, season, episode = parse_stream_id('series', 'tt1480055:s01e02')

        self.assertEqual((tmdb_id, season, episode), (1399, '01', '02'))

    @patch('app.get_series_context_from_imdb')
    @patch('app.get_tmdb_id')
    def test_parse_stream_id_uses_episode_hint_when_imdb_has_no_numbers(
        self, mock_map, mock_hint
    ):
        mock_map.return_value = 1399
        mock_hint.return_value = (1399, 1, 2)

        tmdb_id, season, episode = parse_stream_id('series', 'tt1480055')

        self.assertEqual((tmdb_id, season, episode), (1399, '1', '2'))

    @patch('app.get_series_context_from_imdb')
    @patch('app.get_tmdb_id')
    def test_parse_stream_id_uses_hint_tmdb_when_primary_map_missing(
        self, mock_map, mock_hint
    ):
        mock_map.return_value = None
        mock_hint.return_value = (60574, 1, 1)

        tmdb_id, season, episode = parse_stream_id('series', 'tt1312171')

        self.assertEqual((tmdb_id, season, episode), (60574, '1', '1'))

    def test_parse_stream_id_supports_tmdb_labeled_variant(self):
        tmdb_id, season, episode = parse_stream_id(
            'series',
            'tmdb:tv:224372:season:01:episode:02'
        )

        self.assertEqual((tmdb_id, season, episode), (224372, '01', '02'))

    def test_parse_stream_id_supports_tmdb_slashed_variant(self):
        tmdb_id, season, episode = parse_stream_id('series', 'tmdb/tv/224372/1/2')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '2'))

    def test_parse_stream_id_supports_prefixless_numeric_tmdb_variant(self):
        tmdb_id, season, episode = parse_stream_id('series', '60574:1:1')

        self.assertEqual((tmdb_id, season, episode), (60574, '1', '1'))

    def test_parse_stream_id_supports_prefixless_typed_tmdb_variant(self):
        tmdb_id, season, episode = parse_stream_id('series', 'tv:60574:1:1')

        self.assertEqual((tmdb_id, season, episode), (60574, '1', '1'))

    @patch('app.get_tmdb_id')
    def test_parse_stream_id_supports_urlencoded_imdb_episode(self, mock_map):
        mock_map.return_value = 224372

        tmdb_id, season, episode = parse_stream_id('series', 'tt27497448%3A1%3A1')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '1'))

    @patch('app.get_tmdb_id')
    def test_parse_stream_id_supports_double_urlencoded_imdb_episode(self, mock_map):
        mock_map.return_value = 224372

        tmdb_id, season, episode = parse_stream_id('series', 'tt27497448%253A1%253A1')

        self.assertEqual((tmdb_id, season, episode), (224372, '1', '1'))


if __name__ == '__main__':
    unittest.main()
