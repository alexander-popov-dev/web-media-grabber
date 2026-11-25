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

- Python 3.13+
- `ffmpeg` on `PATH` (required for video download; audio relay works without it)
- Deno >= 2.3 (or Node >= 22) available to yt-dlp — required to solve YouTube's signature challenge.
- `bgutil-ytdlp-pot-provider` (Python plugin + server from the Docker image) — YouTube PO tokens are
  needed to avoid "Sign in to confirm you're not a bot" when running from a server/datacenter IP.
- For Docker, see `deploy/docker-compose.yaml`; the image already contains Deno, ffmpeg, Playwright
  and the PO token provider.

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

`BACKEND_HOST` and `BACKEND_PORT` are optional: they default to `127.0.0.1` and `8000`.
Create a `.env` (or `.env.local`) next to `main.py` to override them:

```ini
DEBUG=TRUE
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

`BACKEND_HOST` is the public hostname used in download links and the Traefik `Host()` rule —
the server itself always binds `0.0.0.0` inside the container. `DEBUG=TRUE` makes format links
point at `http://<host>:<port>`; in production set `DEBUG=FALSE` and they will use
`https://<host>`.

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

### Docker smoke test

```bash
make rebuild-full
make ps
make test                         # uses a known public YouTube video
make test URL=<youtube-url>       # or test a specific video
```

`make test` calls `/api/post/get` and then follows the returned download link through the running
backend, so it verifies metadata extraction and real byte streaming.

## YouTube bot checks

If YouTube answers `Sign in to confirm you're not a bot`, the block comes from the **server's IP**,
not from the cookie file. This was verified directly: the watch page returns
`playabilityStatus: LOGIN_REQUIRED` for the same video with full auth cookies, anonymous cookies,
no cookies, every supported player client and every User-Agent. yt-dlp also drops `LOGIN_INFO`
from its in-memory jar because YouTube sends a cookie-deletion header — that is a symptom of the
IP-level block, not a broken export.

The only reliable fix is a different outbound IP. Set `YOUTUBE_PROXY` in `.env` (it is used by both
yt-dlp and the Playwright cookie refresh):

```ini
YOUTUBE_PROXY=http://user:pass@host:port,http://user2:pass2@host2:port2
```

A comma-separated pool is supported: YouTube also blocks some IP/video pairs individually, so
extraction retries the next endpoint on a bot check and remembers the working one for the
following download request (metadata and download are separate HTTP requests).

Popular videos may still work without a proxy because they are served from YouTube's cache; less
popular videos are checked per request.

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
| `src/backend/download/service.py` | Dispatches to the right platform service; downloads through the platform scraper (yt-dlp with cookies/PO tokens), then falls back to urllib relay or an ffmpeg `-c copy` fragmented MP4 pipe. |
| `src/backend/download/router.py` | `/post/get` and `/post/download` (`response_model=None` because a `StreamingResponse` union is not a valid pydantic response model). |
| `src/backend/download/exceptions.py` | `PlatformNotSupported`, `MediaNotAvailable` — mapped to JSON by the global handler in `main.py`. |

## Notes

- YouTube extraction uses the `mweb`, `tv` and `web_safari` player clients plus generated PO tokens.
  Older yt-dlp releases (< 2026.11.23) break on current YouTube players and must not be used.
- Mount a cookies file at `cookies/cookies_youtube.txt` (either Netscape format or a raw
  `name=value; ...` header; the app normalizes it and fixes the expiry). For best results export it
  from a logged-in YouTube account. Leave `YT_COOKIES_BROWSER` empty in containers — browsers are
  unavailable there and would shadow the mounted file.
- Video downloads are performed by yt-dlp in the same run that extracts cookies, visitor data and
  PO tokens. Fetching a resolved Google Video URL later with plain urllib/ffmpeg often returns 403.
  If yt-dlp cannot download the format, the service falls back to ffmpeg `-c copy` remuxing and then
  to a direct relay.
- Anonymous cookies are enough for many public videos, but YouTube may still answer 403 for a
  particular video from a datacenter IP. Export a logged-in `cookies_youtube.txt` in that case.
- The audio relay sends `Range: bytes=0-`; without it googlevideo throttles to ~34 kB/s, while a
  ranged request is served at full speed and still reports `Content-Length`.
- `.env`, `.env.local`, `.venv`, `__pycache__` are gitignored. `.idea/` is also ignored.

## License

MIT