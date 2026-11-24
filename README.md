# MediaDownloader

MediaDownloader is a FastAPI backend + vanilla-JS frontend that extracts media from YouTube,
Facebook, Instagram and TikTok links and streams the files **through the server** to the browser.
Audio is relayed byte-for-byte; video is merged (video-only DASH + audio) with ffmpeg on the fly
and served as a fragmented MP4, so the browser always receives a single playable file with a proper
`Content-Disposition: attachment` header.

## Supported platforms

- **YouTube** — full metadata + video/audio format lists, server-side ffmpeg merge for DASH video.
- **Facebook** — metadata and downloadable formats via yt-dlp.
- **Instagram** — Reels, posts and videos metadata + downloadable formats.
- **TikTok** — video metadata + downloadable formats.

## Features

- **Vanilla JS + Tailwind CDN** frontend — no build step, no framework, one `index.html`.
- **FastAPI backend** with Dishka DI, two endpoints:
  - `GET /api/post/get?url=<platform-url>` — post metadata + available video/audio formats.
  - `GET /api/post/download?url=<...>&height=<H>` — video quality `H`, merged via ffmpeg, streamed as MP4.
  - `GET /api/post/download?url=<...>&format_id=<id>` — single audio format, relayed as-is.
- **Server-side streaming** (no `RedirectResponse`): media host URLs carry `ip=` of the server,
  so a browser redirect would 403; the backend relays/merges and the client downloads from the
  same origin.
- **Retry/backoff** on temporary HTTP 403/429 rate limits from media hosts.
- **Content-Length** passed through for audio so the browser shows real download progress.
- English comments and docstrings throughout.

## Requirements

- Python 3.10+
- `ffmpeg` on `PATH` (required for video download; audio relay works without it)
- Node.js runtime available to yt-dlp (`js_runtimes={"node": {}}`) — required to solve YouTube's
  signature challenge and keep progressive formats in the extraction result.

## Installation

```bash
# clone
git clone git@github.com:alexander-popov-dev/media-downloader.git
cd media-downloader

# create venv and install dependencies
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux/macOS

pip install -e .
```

Create a `.env` (or `.env.local`) next to `main.py`:

```ini
DEBUG=TRUE
SECRET_KEY=change-me
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

`DEBUG=TRUE` makes format links point at `http://<host>:<port>`; in production set `DEBUG=FALSE`
and they will use `https://<host>`.

## Run

```bash
python main.py
```

The app serves:
- `http://127.0.0.1:8000/` — frontend (StaticFiles)
- `http://127.0.0.1:8000/api/post/get?url=<youtube-url>` — metadata
- `http://127.0.0.1:8000/api/post/download?url=<youtube-url>&height=720` — video stream
- `http://127.0.0.1:8000/api/post/download?url=<youtube-url>&format_id=140` — audio stream
- `http://127.0.0.1:8000/openapi.json` — OpenAPI schema

Open the frontend, paste a YouTube link, click **Download**, pick a quality, and the file starts
downloading from the browser.

## API

`GET /api/post/get`

Query: `url` (string) — YouTube page URL.

Response (JSON): `Post` with `title`, `author`, `thumbnail`, `duration`, `videos[]` and `audios[]`.
Each `Video` carries `format`, `resolution`, `size` and a same-origin `/api/post/download?height=H`
link; each `Audio` carries `format`, `bitrate`, `size` and a `?format_id=<id>` link.

`GET /api/post/download`

Query: `url`, plus exactly one of:
- `height=<int>` — video quality (merged with audio by ffmpeg, served as MP4).
- `format_id=<string>` — single audio format, relayed as-is.

Optional `title=<string>` sets the downloaded file name.

Response: `StreamingResponse` with `Content-Disposition: attachment`. Video is `video/mp4`;
audio keeps its upstream media type.

Unsupported platforms and extraction failures return JSON errors (`400` / `502`), never a raw
traceback.

## Architecture

| Layer | Responsibility |
|---|---|
| `src/frontend/index.html` | Vanilla UI: URL input, fetch metadata, render formats, trigger download. |
| `src/platforms/core/scraper.py` | Base yt-dlp extraction with retry/backoff, socket timeouts, `js_runtimes`. |
| `src/platforms/core/parser.py` | Base parser: yt-dlp info → `Post`/`Video`/`Audio` schemas, size via `tbr` fallback. |
| `src/platforms/core/service.py` | `PlatformService` protocol + `BasePlatformService` delegation to scraper/parser. |
| `src/platforms/youtube/scraper.py` | YouTube scraper: `js_runtimes`+`remote_components`, DASH video/audio splitting. |
| `src/platforms/youtube/service.py` | YouTube service facade (`PLATFORM = "youtube"`). |
| `src/platforms/youtube/parser.py` | YouTube parser: mp4/webm video, m4a/webm/mp3/aac/opus audio. |
| `src/platforms/generic/scraper.py` | Generic scraper for Facebook/Instagram/TikTok (no remote_components). |
| `src/platforms/{facebook,instagram,tiktok}/service.py` | Per-platform service facades (`PLATFORM` markers). |
| `src/backend/download/service.py` | Dispatches to the right platform service; `stream_audio` (urllib relay with `Range`) and `stream_video` (ffmpeg `-c copy` fragmented MP4 into `pipe:1`, client-disconnect kill). |
| `src/backend/download/router.py` | `/post/get` and `/post/download` (`response_model=None` because a `StreamingResponse` union is not a valid pydantic response model). |
| `src/backend/download/exceptions.py` | `PlatformNotSupported`, `MediaNotAvailable` — mapped to JSON by the global handler in `main.py`. |

## Notes

- Video is downloaded as DASH (video without audio), so ffmpeg remuxes `-c copy` into a fragmented
  MP4 (`frag_keyframe+empty_moov`) streamed through a pipe — a regular MP4 header cannot be written
  before the total size is known, which never happens while streaming.
- Audio relay sends `Range: bytes=0-`; without it googlevideo throttles to ~34 kB/s, while a ranged
  request is served at full speed and still reports `Content-Length`.
- `.env`, `.env.local`, `.venv`, `__pycache__` are gitignored. `.idea/` is also ignored.

## License

MIT