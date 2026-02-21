import base64
import json
import logging


logger = logging.getLogger(__name__)

ALLOWED_WYZIE_SOURCES = {
    "all",
    "opensubtitles",
    "subdl",
    "subf2m",
    "podnapisi",
    "gestdown",
    "animetosho",
}

DEFAULT_ADDON_CONFIG = {
    "enable_vidzee": True,
    "enable_autoembed": True,
    "enable_vixsrc": True,
    "enable_aniways": True,
    "enable_stmify": True,
    "enable_hdhub4u": True,
    "enable_moviehdzone": True,
    "enable_wyzie": True,
    "wyzie_languages": ["en"],
    "wyzie_formats": ["srt", "ass"],
    "wyzie_source": "all",
    "wyzie_hearing_impaired": False,
    "wyzie_max_results": 8,
    "wyzie_apply_to_aniways_ids": True,
}


def _default_config_copy():
    return {
        "enable_vidzee": DEFAULT_ADDON_CONFIG["enable_vidzee"],
        "enable_autoembed": DEFAULT_ADDON_CONFIG["enable_autoembed"],
        "enable_vixsrc": DEFAULT_ADDON_CONFIG["enable_vixsrc"],
        "enable_aniways": DEFAULT_ADDON_CONFIG["enable_aniways"],
        "enable_stmify": DEFAULT_ADDON_CONFIG["enable_stmify"],
        "enable_hdhub4u": DEFAULT_ADDON_CONFIG["enable_hdhub4u"],
        "enable_moviehdzone": DEFAULT_ADDON_CONFIG["enable_moviehdzone"],
        "enable_wyzie": DEFAULT_ADDON_CONFIG["enable_wyzie"],
        "wyzie_languages": list(DEFAULT_ADDON_CONFIG["wyzie_languages"]),
        "wyzie_formats": list(DEFAULT_ADDON_CONFIG["wyzie_formats"]),
        "wyzie_source": DEFAULT_ADDON_CONFIG["wyzie_source"],
        "wyzie_hearing_impaired": DEFAULT_ADDON_CONFIG["wyzie_hearing_impaired"],
        "wyzie_max_results": DEFAULT_ADDON_CONFIG["wyzie_max_results"],
        "wyzie_apply_to_aniways_ids": DEFAULT_ADDON_CONFIG["wyzie_apply_to_aniways_ids"],
    }


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _unique_tokens(values, lower=True):
    normalized = []
    seen = set()
    for item in values:
        token = str(item or "").strip()
        if not token:
            continue
        if lower:
            token = token.lower()
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _parse_csv_list(value, lower=True):
    if value is None:
        return []
    if isinstance(value, str):
        return _unique_tokens(value.split(","), lower=lower)
    if isinstance(value, (list, tuple, set)):
        return _unique_tokens(list(value), lower=lower)
    return []


def normalize_addon_config(raw_config):
    cfg = _default_config_copy()
    if not isinstance(raw_config, dict):
        return cfg

    cfg["enable_vidzee"] = _to_bool(raw_config.get("enable_vidzee"), cfg["enable_vidzee"])
    cfg["enable_autoembed"] = _to_bool(raw_config.get("enable_autoembed"), cfg["enable_autoembed"])
    cfg["enable_vixsrc"] = _to_bool(raw_config.get("enable_vixsrc"), cfg["enable_vixsrc"])
    cfg["enable_aniways"] = _to_bool(raw_config.get("enable_aniways"), cfg["enable_aniways"])
    cfg["enable_stmify"] = _to_bool(raw_config.get("enable_stmify"), cfg["enable_stmify"])
    cfg["enable_hdhub4u"] = _to_bool(raw_config.get("enable_hdhub4u"), cfg["enable_hdhub4u"])
    cfg["enable_moviehdzone"] = _to_bool(raw_config.get("enable_moviehdzone"), cfg["enable_moviehdzone"])
    cfg["enable_wyzie"] = _to_bool(raw_config.get("enable_wyzie"), cfg["enable_wyzie"])
    cfg["wyzie_hearing_impaired"] = _to_bool(
        raw_config.get("wyzie_hearing_impaired"),
        cfg["wyzie_hearing_impaired"],
    )
    cfg["wyzie_apply_to_aniways_ids"] = _to_bool(
        raw_config.get("wyzie_apply_to_aniways_ids"),
        cfg["wyzie_apply_to_aniways_ids"],
    )

    languages = _parse_csv_list(raw_config.get("wyzie_languages"), lower=True)
    if languages:
        cfg["wyzie_languages"] = languages[:12]

    formats = _parse_csv_list(raw_config.get("wyzie_formats"), lower=True)
    if formats:
        cfg["wyzie_formats"] = formats[:8]

    source = str(raw_config.get("wyzie_source") or "").strip().lower()
    if source in ALLOWED_WYZIE_SOURCES:
        cfg["wyzie_source"] = source

    raw_limit = raw_config.get("wyzie_max_results")
    try:
        limit = int(raw_limit)
        limit = max(1, min(limit, 30))
        cfg["wyzie_max_results"] = limit
    except Exception:
        pass

    return cfg


def encode_addon_config(raw_config):
    cfg = normalize_addon_config(raw_config)
    packed = json.dumps(cfg, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(packed.encode("utf-8")).decode("ascii").rstrip("=")


def decode_addon_config_token(token):
    raw = str(token or "").strip()
    if not raw:
        return _default_config_copy()

    try:
        padded = raw + ("=" * (-len(raw) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        logger.warning("Failed to parse config token, using defaults: %s", exc)
        return _default_config_copy()

    return normalize_addon_config(payload)
