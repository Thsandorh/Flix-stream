import sys
import os
import unittest
import base64
import json
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import fetch_aniways_streams, ANIWAYS_API_BASE

class TestMegaplayFix(unittest.TestCase):
    @patch('app.requests.get')
    def test_megaplay_proxy_removed(self, mock_get):
        anime_id = "test_anime"
        episode_num = "1"
        episode_id = "ep_1"
        server_id = "srv_megaplay"

        # Create valid proxyHls with headers
        headers_payload = json.dumps({"referer": "https://rapid-cloud.co/", "origin": "https://rapid-cloud.co"})
        b64_headers = base64.b64encode(headers_payload.encode()).decode()
        proxy_hls = f"/proxy/megaplay/{b64_headers}/some_url"

        # Mock responses
        # 1. Episodes
        mock_ep_resp = MagicMock()
        mock_ep_resp.status_code = 200
        mock_ep_resp.json.return_value = [{"number": "1", "id": episode_id}]

        # 2. Servers
        mock_srv_resp = MagicMock()
        mock_srv_resp.status_code = 200
        mock_srv_resp.json.return_value = [{
            "serverId": server_id,
            "serverName": "Megaplay",
            "type": "sub"
        }]

        # 3. Stream
        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 200
        mock_stream_resp.json.return_value = {
            "source": {
                "hls": "https://stormshade84.live/master.m3u8",
                "proxyHls": proxy_hls,
            },
            "url": "https://stormshade84.live/master.m3u8"
        }

        # Configure side_effect based on URL
        def side_effect(url, **kwargs):
            if "/episodes/servers/" in url:
                return mock_stream_resp
            elif "/episodes/" in url and "/servers" in url:
                return mock_srv_resp
            elif "/episodes" in url:
                return mock_ep_resp
            return MagicMock(status_code=404)

        mock_get.side_effect = side_effect

        streams = fetch_aniways_streams(anime_id, episode_num)

        print("\nReturned streams:")
        for s in streams:
            print(f"- {s['url']}")
            print(f"  Headers: {s.get('behaviorHints', {}).get('proxyHeaders', {}).get('request', {})}")

        # Assertions
        urls = [s['url'] for s in streams]

        # Check direct link is present
        self.assertIn("https://stormshade84.live/master.m3u8", urls)

        # Check proxy link is ABSENT
        has_proxy = any("/proxy/megaplay/" in u for u in urls)
        self.assertFalse(has_proxy, "Megaplay proxy link should be filtered out")

        # Check headers for direct link
        # Find the stream object for direct link
        direct_stream = next(s for s in streams if s['url'] == "https://stormshade84.live/master.m3u8")
        headers = direct_stream['behaviorHints']['proxyHeaders']['request']
        self.assertEqual(headers.get('Referer'), "https://rapid-cloud.co/")
        self.assertEqual(headers.get('Origin'), "https://rapid-cloud.co")

if __name__ == '__main__':
    unittest.main()
