from hydrahd_integration import get_hydrahd_streams

def test_hydrahd():
    # Inception
    imdb_id = "tt1375666"
    tmdb_id = "27205"

    print(f"Fetching streams for {imdb_id} / {tmdb_id}...")
    streams = get_hydrahd_streams(imdb_id, tmdb_id)

    if not streams:
        print("No streams found.")
    else:
        print(f"Found {len(streams)} streams:")
        for stream in streams:
            print(f"- {stream['name']}: {stream['url']}")

if __name__ == "__main__":
    test_hydrahd()
