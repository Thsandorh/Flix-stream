from app import app
import json

def test_stream_endpoint():
    client = app.test_client()
    response = client.get("/stream/movie/tt6263850.json")
    data = response.get_json()
    streams = data.get("streams", [])
    print(f"Total streams: {len(streams)}")
    for i, s in enumerate(streams[:20]):
        print(f"{i}: [{s.get('name')}] {s.get('title')}")

if __name__ == "__main__":
    test_stream_endpoint()
