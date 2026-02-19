import unittest
from unittest.mock import patch

from app import get_tmdb_id


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
    def test_movie_prefers_movie_result(self, mock_get):
        mock_get.return_value = MockResponse({
            'movie_results': [{'id': 27205}],
            'tv_results': [{'id': 1399}],
            'tv_episode_results': [],
        })

        tmdb_id = get_tmdb_id('tt1375666', 'movie')

        self.assertEqual(tmdb_id, 27205)


if __name__ == '__main__':
    unittest.main()
