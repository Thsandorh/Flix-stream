import sys
from unittest.mock import MagicMock, patch

# Mock dependencies
mock_flask = MagicMock()
sys.modules['flask'] = mock_flask
mock_app = MagicMock()
mock_flask.Flask.return_value = mock_app

def mock_decorator(f):
    return f

mock_app.route.return_value = mock_decorator
mock_flask.jsonify = lambda x: x

sys.modules['requests'] = MagicMock()
sys.modules['Crypto'] = MagicMock()
sys.modules['Crypto.Cipher'] = MagicMock()

import unittest
import re

# Now I can import app
import app

class TestValidation(unittest.TestCase):

    @patch('app.get_tmdb_id')
    @patch('app.get_decryption_key')
    def test_valid_movie(self, mock_key, mock_tmdb):
        mock_tmdb.return_value = '123'
        mock_key.return_value = None # Stop there

        result = app.stream('movie', 'tt1234567')
        mock_tmdb.assert_called_once_with('tt1234567')

    def test_invalid_movie_format(self):
        result = app.stream('movie', '1234567')
        self.assertEqual(result, {"streams": []})

    def test_invalid_movie_parts(self):
        result = app.stream('movie', 'tt1234567:1:1')
        self.assertEqual(result, {"streams": []})

    @patch('app.get_tmdb_id')
    @patch('app.get_decryption_key')
    def test_valid_series(self, mock_key, mock_tmdb):
        mock_tmdb.return_value = '123'
        mock_key.return_value = None
        result = app.stream('series', 'tt1234567:1:1')
        mock_tmdb.assert_called_once_with('tt1234567')

    def test_invalid_series_format(self):
        result = app.stream('series', 'tt1234567:1')
        self.assertEqual(result, {"streams": []})

    def test_invalid_series_non_numeric(self):
        result = app.stream('series', 'tt1234567:s1:e1')
        self.assertEqual(result, {"streams": []})

    def test_invalid_type(self):
        result = app.stream('invalid', 'tt1234567')
        self.assertEqual(result, {"streams": []})

    def test_malicious_id(self):
        result = app.stream('movie', 'tt1234567/../../test')
        self.assertEqual(result, {"streams": []})

if __name__ == '__main__':
    unittest.main()
