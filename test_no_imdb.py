from flix_stream.cineby import CinebyProvider
import json
import logging
import os
import sys

# Ensure flix_stream is importable
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)

def verify_no_imdb():
    # Deadpool & Wolverine
    tmdb_id = 533535
    print(f"Testing final CinebyProvider WITHOUT IMDB...")
    streams = CinebyProvider.fetch_streams(tmdb_id, imdb_id=None)
    print(f"Found {len(streams)} streams.")
    for s in streams:
        print(f"[{s['name']}] {s['title']}: {s['url'][:60]}...")

if __name__ == "__main__":
    verify_no_imdb()
