import unittest
from unittest.mock import Mock, patch

from flix_stream.stmify import get_stmify_catalog, get_stmify_stream


class TestStmify(unittest.TestCase):
    def tearDown(self):
        get_stmify_catalog.cache_clear()

    @patch("flix_stream.stmify.requests.get")
    def test_get_stmify_catalog_parses_archive_items(self, mock_get):
        html = """
        <div class="archive-item">
          <a href="https://stmify.com/live-tv/tv1/">
            <img data-src="https://img.example/tv1.jpg" alt="TV1" />
          </a>
        </div>
        """
        response = Mock()
        response.text = html
        response.raise_for_status = Mock()
        mock_get.return_value = response

        metas = get_stmify_catalog(1)
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["id"], "stmify:tv1")
        self.assertEqual(metas[0]["type"], "series")
        self.assertEqual(metas[0]["name"], "TV1")

    @patch("flix_stream.stmify.requests.get")
    def test_get_stmify_stream_resolves_url(self, mock_get):
        channel_response = Mock()
        channel_response.text = '<iframe src="//cdn.stmify.com/embed-free/v1/tv1-lt-jw"></iframe>'
        channel_response.raise_for_status = Mock()

        embed_response = Mock()
        embed_response.text = 'const streamId = "TV1"; const country = "lt";'
        embed_response.raise_for_status = Mock()

        api_response = Mock()
        api_response.raise_for_status = Mock()
        api_response.json.return_value = {"TV1": {"url": "https://stream.example/live.m3u8"}}

        mock_get.side_effect = [channel_response, embed_response, api_response]
        streams = get_stmify_stream("stmify:tv1")

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["name"], "Stmify")
        self.assertEqual(streams[0]["url"], "https://stream.example/live.m3u8")


if __name__ == "__main__":
    unittest.main()
