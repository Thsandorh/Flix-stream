import unittest
from unittest.mock import Mock, patch

from flix_stream.runtime_config import DEFAULT_ADDON_CONFIG
from flix_stream.wyzie import fetch_wyzie_subtitles, merge_subtitles


class TestWyzie(unittest.TestCase):
    @patch("flix_stream.wyzie.requests.get")
    def test_fetch_wyzie_subtitles_maps_response_and_dedupes(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "1",
                "url": "https://sub.example/a.srt",
                "language": "en",
                "source": "opensubtitles",
                "format": "srt",
            },
            {
                "id": "2",
                "url": "https://sub.example/a.srt",
                "language": "en",
                "source": "opensubtitles",
                "format": "srt",
            },
        ]
        mock_get.return_value = mock_response

        cfg = dict(DEFAULT_ADDON_CONFIG)
        cfg["wyzie_max_results"] = 5
        subtitles = fetch_wyzie_subtitles(12345, "1", "2", cfg)

        self.assertEqual(len(subtitles), 1)
        self.assertEqual(subtitles[0]["lang"], "en")
        self.assertEqual(subtitles[0]["url"], "https://sub.example/a.srt")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["id"], "12345")
        self.assertEqual(kwargs["params"]["season"], "1")
        self.assertEqual(kwargs["params"]["episode"], "2")

    def test_merge_subtitles_keeps_order_and_uniques(self):
        merged = merge_subtitles(
            [{"url": "https://a", "lang": "en"}, {"url": "https://b", "lang": "hu"}],
            [{"url": "https://b", "lang": "fr"}, {"url": "https://c", "lang": "ja"}],
        )
        self.assertEqual([item["url"] for item in merged], ["https://a", "https://b", "https://c"])


if __name__ == "__main__":
    unittest.main()
