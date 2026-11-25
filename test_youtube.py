"""Small end-to-end smoke test for the YouTube pipeline.

Usage (inside the container):
    python test_youtube.py [youtube-url]

Environment:
    API_BASE_URL  defaults to http://localhost:8000/api
"""

import json
import os
import sys
import urllib.parse
import urllib.request

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api").rstrip("/")
# A public video that does not require authenticated cookies; pass another URL
# as the first argument to test a specific post.
DEFAULT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def get_json(path: str, params: dict[str, str]) -> dict:
    url = f"{API_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=90) as response:
        return json.load(response)


def main() -> int:
    video_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    payload = get_json("/post/get", {"url": video_url})
    post = payload["post"]
    videos = post.get("videos") or []
    print(f"metadata: {post.get('title')!r}, {len(videos)} video qualities")
    if not videos:
        print("FAIL: no video formats returned")
        return 1

    # Metadata links use the public host (BACKEND_HOST). When testing from
    # inside the container that host may not be reachable via hairpin NAT, so
    # keep the query and point the request at the API base actually being used.
    api_parts = urllib.parse.urlsplit(API_BASE_URL)
    link_parts = urllib.parse.urlsplit(videos[-1]["url"])
    download_url = urllib.parse.urlunsplit(
        (api_parts.scheme, api_parts.netloc, link_parts.path, link_parts.query, "")
    )
    request = urllib.request.Request(download_url, headers={"Range": "bytes=0-1023"})
    with urllib.request.urlopen(request, timeout=120) as response:
        chunk = response.read()
        print(f"download: HTTP {response.status}, {len(chunk)} bytes, {response.headers.get('Content-Type')}")
    if len(chunk) < 16:
        print("FAIL: download returned too few bytes")
        return 1
    print("OK: YouTube extraction and streaming work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
