import re
from urllib.parse import unquote


def decode_stream_id(raw_id):
    """Decode URL-encoded stream ids, including double-encoded variants."""
    decoded = str(raw_id or "")
    for _ in range(2):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded


def normalize_episode_part(value):
    if value is None:
        return None
    token = str(value).strip()
    if not token:
        return None
    if token.isdigit():
        return str(int(token))
    match = re.search(r"\d+", token)
    if match:
        return str(int(match.group(0)))
    return None


def provider_rank(stream_obj):
    name = str(stream_obj.get("name", "")).lower()
    if name.startswith("vidzee"):
        return 0
    if name.startswith("autoembed"):
        return 1
    if name.startswith("vixsrc"):
        return 2
    if name.startswith("cineby"):
        return 3
    if name.startswith("aniways"):
        return 4
    return 5
