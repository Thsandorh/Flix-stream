import unittest

from flix_stream.runtime_config import (
    DEFAULT_ADDON_CONFIG,
    decode_addon_config_token,
    encode_addon_config,
    normalize_addon_config,
)


class TestRuntimeConfig(unittest.TestCase):
    def test_invalid_token_falls_back_to_defaults(self):
        cfg = decode_addon_config_token("not-a-valid-token")
        self.assertEqual(cfg, DEFAULT_ADDON_CONFIG)

    def test_roundtrip_and_normalization(self):
        raw = {
            "enable_wyzie": "false",
            "enable_vidzee": "0",
            "wyzie_languages": "en,hu,en,",
            "wyzie_formats": ["srt", "ASS", "srt"],
            "wyzie_source": "animetosho",
            "wyzie_max_results": "999",
            "wyzie_hearing_impaired": "yes",
        }
        token = encode_addon_config(raw)
        cfg = decode_addon_config_token(token)

        self.assertFalse(cfg["enable_wyzie"])
        self.assertFalse(cfg["enable_vidzee"])
        self.assertEqual(cfg["wyzie_languages"], ["en", "hu"])
        self.assertEqual(cfg["wyzie_formats"], ["srt", "ass"])
        self.assertEqual(cfg["wyzie_source"], "animetosho")
        self.assertEqual(cfg["wyzie_max_results"], 30)
        self.assertTrue(cfg["wyzie_hearing_impaired"])

    def test_normalize_non_dict(self):
        cfg = normalize_addon_config(None)
        self.assertEqual(cfg, DEFAULT_ADDON_CONFIG)


if __name__ == "__main__":
    unittest.main()
