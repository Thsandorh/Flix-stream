import re

from flix_stream.config import LANG_MAP


def parse_subtitles(subtitle_list):
    """Parses subtitle list into Stremio format."""
    parsed = []
    if not subtitle_list:
        return parsed

    for sub in subtitle_list:
        lang_name = sub.get("lang", "")
        url = sub.get("url", "")
        if not url:
            continue

        # Try to map language name to ISO 639-2.
        iso_code = LANG_MAP.get(lang_name)
        if not iso_code:
            # Try stripping numbers at end: "English2" -> "English".
            base_lang = re.sub(r"\d+$", "", lang_name).strip()
            iso_code = LANG_MAP.get(base_lang)

        if not iso_code:
            # Fall back to source language name when no mapping exists.
            iso_code = lang_name

        parsed.append({"url": url, "lang": iso_code, "id": lang_name})
    return parsed
