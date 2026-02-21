import logging
import re
import requests
from flix_stream.config import COMMON_HEADERS, SUPEREMBED_BASE_URL, PROVIDER_CACHE_TTL, PROVIDER_CACHE_MAXSIZE
from flix_stream.cache import ttl_cache
from flix_stream.subtitles import parse_subtitles
from flix_stream.tmdb import get_imdb_id_from_tmdb

logger = logging.getLogger(__name__)

# List of server IDs that are known to be "VIP" and easier to scrape
VIP_SERVERS = ["88", "89", "90"]

@ttl_cache(ttl_seconds=PROVIDER_CACHE_TTL, maxsize=PROVIDER_CACHE_MAXSIZE)
def fetch_superembed_streams(tmdb_id, content_type, season, episode):
    """
    Scrapes SuperEmbed for direct playable links.
    """
    imdb_id = get_imdb_id_from_tmdb(tmdb_id, content_type)
    if not imdb_id:
        logger.warning(f"Could not resolve IMDb ID for TMDB {tmdb_id}")
        return []

    session = requests.Session()
    session.headers.update(COMMON_HEADERS)

    streams = []
    try:
        # 1. Get play token from multiembed.mov
        media_type = "tv" if str(content_type or "").lower() in ("series", "tv") else "movie"
        if media_type == "tv":
            url = f"{SUPEREMBED_BASE_URL}/?video_id={imdb_id}&s={season}&e={episode}"
        else:
            url = f"{SUPEREMBED_BASE_URL}/?video_id={imdb_id}"

        r1 = session.get(url, allow_redirects=True, timeout=10)
        token_match = re.search(r'play=([^&]+)', r1.url)
        if not token_match:
            return []
        token = token_match.group(1)
        player_host = r1.url.split('/?')[0] # Usually https://streamingnow.mov

        # 2. Get server list from response.php
        r2 = session.post(f"{player_host}/response.php",
                          data={"token": token},
                          headers={
                              "Referer": r1.url,
                              "X-Requested-With": "XMLHttpRequest"
                          },
                          timeout=10)

        if r2.status_code != 200:
            return []

        server_list = re.findall(r'<li data-id="([^"]+)" data-server="([^"]+)"', r2.text)

        # 3. Scrape each server, prioritized
        # Sort so VIP servers come first
        server_list.sort(key=lambda x: 0 if x[1] in VIP_SERVERS else 1)

        for sid, srv in server_list:
            try:
                # Limit to VIP servers for now to ensure quality/playability, or add others as iframes
                play_url = f"{player_host}/playvideo.php?video_id={sid}&server_id={srv}&token={token}&init=0"
                r3 = session.get(play_url, headers={"Referer": r1.url}, timeout=10)

                iframe_match = re.search(r'<iframe.*?src="([^"]+)"', r3.text)
                if not iframe_match:
                    continue

                iframe_url = iframe_match.group(1)
                if iframe_url.startswith("//"):
                    iframe_url = "https:" + iframe_url
                elif iframe_url.startswith("/"):
                    iframe_url = f"{player_host}{iframe_url}"

                # Check if it's a VIP stream (internal)
                if "vipstream_vfx.php" in iframe_url:
                    r4 = session.get(iframe_url, headers={"Referer": player_host}, timeout=10)
                    file_match = re.search(r'file\s*:\s*"([^"]+)"', r4.text)
                    if file_match:
                        m3u8_url = file_match.group(1)

                        # Extract subtitles
                        subs = []
                        sub_match = re.search(r'subtitle\s*:\s*"([^"]+)"', r4.text)
                        if sub_match:
                            sub_str = sub_match.group(1)
                            # Format: [Lang]Url,[Lang]Url
                            parts = sub_str.split(',')
                            for p in parts:
                                if ']' in p:
                                    label, url = p.split(']', 1)
                                    subs.append({"lang": label[1:], "url": url})

                        streams.append({
                            "name": f"SuperEmbed VIP-{srv}",
                            "title": f"[SuperEmbed] Direct M3U8 ({srv})\nSubtitles: {len(subs)}",
                            "url": m3u8_url,
                            "subtitles": parse_subtitles(subs),
                            "behaviorHints": {
                                "notWebReady": True,
                                "proxyHeaders": {"request": COMMON_HEADERS}
                            }
                        })
                else:
                    # Generic iframe fallback
                    # We can't always extract direct links from 3rd party hosters easily
                    # But we can provide the iframe URL if it's not blocked
                    # Some clients can play these if they support iframe playback
                    streams.append({
                        "name": f"SuperEmbed {srv}",
                        "title": f"[SuperEmbed] Iframe ({srv})",
                        "url": iframe_url,
                        "behaviorHints": {
                            "notWebReady": True,
                        }
                    })

                # If we found at least one good VIP stream, we can stop or continue
                if len(streams) >= 3:
                    break

            except Exception as e:
                logger.error(f"Error scraping SuperEmbed server {srv}: {e}")
                continue

    except Exception as e:
        logger.error(f"SuperEmbed scraping failed: {e}")

    return streams
