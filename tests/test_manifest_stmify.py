import unittest
from unittest.mock import patch

from app import _build_manifest, app
from flix_stream.runtime_config import DEFAULT_ADDON_CONFIG, encode_addon_config


class TestManifestStmify(unittest.TestCase):
    def test_manifest_includes_stmify_when_enabled(self):
        cfg = dict(DEFAULT_ADDON_CONFIG)
        cfg["enable_stmify"] = True

        with app.test_request_context("/manifest.json"):
            manifest_data = _build_manifest(cfg)

        self.assertIn("stmify", manifest_data.get("idPrefixes", []))
        self.assertIn("catalog", manifest_data.get("resources", []))
        catalog_ids = [item.get("id") for item in manifest_data.get("catalogs", []) if isinstance(item, dict)]
        self.assertIn("stmify-live", catalog_ids)

    def test_manifest_hides_stmify_when_disabled(self):
        cfg = dict(DEFAULT_ADDON_CONFIG)
        cfg["enable_stmify"] = False

        with app.test_request_context("/manifest.json"):
            manifest_data = _build_manifest(cfg)

        self.assertNotIn("stmify", manifest_data.get("idPrefixes", []))
        catalog_ids = [item.get("id") for item in manifest_data.get("catalogs", []) if isinstance(item, dict)]
        self.assertNotIn("stmify-live", catalog_ids)

    @patch("app.get_stmify_catalog")
    def test_catalog_route_respects_toggle(self, mock_catalog):
        mock_catalog.return_value = [{"id": "stmify:tv1", "type": "series", "name": "TV1"}]
        client = app.test_client()

        enabled_token = encode_addon_config({"enable_stmify": True})
        disabled_token = encode_addon_config({"enable_stmify": False})

        enabled_response = client.get(f"/{enabled_token}/catalog/series/stmify-live.json")
        disabled_response = client.get(f"/{disabled_token}/catalog/series/stmify-live.json")

        self.assertEqual(enabled_response.status_code, 200)
        self.assertEqual(enabled_response.get_json(), {"metas": mock_catalog.return_value})
        self.assertEqual(disabled_response.status_code, 200)
        self.assertEqual(disabled_response.get_json(), {"metas": []})

    @patch("app.get_stmify_stream")
    def test_stream_route_respects_toggle(self, mock_stream):
        mock_stream.return_value = [{"name": "Stmify", "url": "https://stream.example/live.m3u8"}]
        client = app.test_client()

        enabled_token = encode_addon_config({"enable_stmify": True})
        disabled_token = encode_addon_config({"enable_stmify": False})

        enabled_response = client.get(f"/{enabled_token}/stream/series/stmify:tv1.json")
        disabled_response = client.get(f"/{disabled_token}/stream/series/stmify:tv1.json")

        self.assertEqual(enabled_response.status_code, 200)
        enabled_payload = enabled_response.get_json()
        self.assertTrue(isinstance(enabled_payload.get("streams"), list))
        self.assertGreaterEqual(len(enabled_payload["streams"]), 1)

        self.assertEqual(disabled_response.status_code, 200)
        self.assertEqual(disabled_response.get_json(), {"streams": []})

    def test_stmify_meta_route_is_not_implemented_and_returns_404(self):
        client = app.test_client()
        response = client.get("/meta/series/stmify:tv1.json")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
