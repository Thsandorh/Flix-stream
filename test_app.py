from app import app
import json

def test_stream_endpoint():
    client = app.test_client()
    # tt6263850 is Deadpool & Wolverine
    response = client.get("/stream/movie/tt6263850.json")
    print(f"Status: {response.status_code}")
    data = response.get_json()
    streams = data.get("streams", [])
    print(f"Total streams: {len(streams)}")
    cineby_streams = [s for s in streams if "Cineby" in s.get("name", "")]
    print(f"Cineby streams: {len(cineby_streams)}")
    for s in cineby_streams:
        print(f"[{s['name']}] {s['title']}: {s['url'][:60]}...")

if __name__ == "__main__":
    test_stream_endpoint()
