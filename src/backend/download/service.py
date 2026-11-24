"""Streaming logic of the download layer.

The service turns resolved platform links into HTTP streams: audio bytes are
relayed from the upstream host, while video is stitched on the fly with ffmpeg
and pushed to the client as a fragmented MP4.

It is platform-agnostic: it holds all registered platform services and
dispatches each request to the one whose ``PLATFORM`` marker matches the URL.
"""
import asyncio
import contextlib
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from starlette.responses import StreamingResponse

from src.backend.download.exceptions import MediaNotAvailable, PlatformNotSupported
from src.backend.download.schemas import DownloadRequest, DownloadResponse
from src.platforms.core.schemas import ResolvedAudio, ResolvedStreams
from src.platforms.core.service import PlatformService

logger = logging.getLogger(__name__)

# Size of a single chunk pushed to the client.
_CHUNK_SIZE = 64 * 1024

# Browser-like user agent: the media host occasionally rejects unknown clients.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Referer header for media CDN hosts that require it (Instagram, Facebook, TikTok).
# Without it, Instagram CDN returns an HTML consent/login page instead of video.
_CDN_REFERERS = {
    "fbcdn.net": "https://www.instagram.com/",
    "instagram.com": "https://www.instagram.com/",
    "facebook.com": "https://www.facebook.com/",
    "tiktok.com": "https://www.tiktok.com/",
}

# Delay (seconds) before each retry against the upstream media host, which
# answers with a temporary HTTP 403 while rate-limiting a client IP.
_RETRY_DELAYS = (1.0, 2.5, 5.0)

# Extensions that always map to a known media type.
_CONTENT_TYPES = {
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
}

# Characters that are not allowed inside a downloadable file name.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(value: str, fallback: str = "media") -> str:
    """Strip characters that are illegal in file names and cap the length."""
    cleaned = _INVALID_FILENAME_CHARS.sub("", value or "").strip().strip(".")
    return (cleaned[:150] or fallback)


def _content_disposition(filename: str) -> str:
    """Build a ``Content-Disposition`` header safe for non-ASCII titles.

    A plain ASCII fallback is provided for old clients while modern browsers
    receive the properly percent-encoded UTF-8 name.
    """
    fallback = filename.encode("ascii", "ignore").decode()
    fallback = re.sub(r"\s+", " ", fallback).strip() or "media"
    encoded = urllib.parse.quote(filename, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


class DownloadService:
    """Turns resolved platform links into HTTP responses streamed to a browser."""

    def __init__(
            self,
            services: list[PlatformService]
    ) -> None:
        self._services = {service.PLATFORM: service for service in services}

    def _get_service(self, url: str) -> PlatformService:
        """Pick the platform service whose marker appears in the URL.

        Raises:
            PlatformNotSupported: When no known platform marker is present.
        """
        lowered = url.lower()
        for platform, service in self._services.items():
            if platform in lowered:
                return service
        raise PlatformNotSupported(f"Unsupported platform for url: {url}")

    async def get_download_url(self, request: DownloadRequest) -> DownloadResponse:
        """Fetch and parse metadata of the given post.

        Raises:
            PlatformNotSupported: When the URL does not belong to a platform
                this server knows how to handle.
            MediaNotAvailable: When the upstream host cannot be extracted.
        """
        service = self._get_service(request.url)

        try:
            post = await service.get_post_info(url=request.url)
        except Exception as exc:  # noqa: BLE001 - reported to the client as a 5xx
            raise MediaNotAvailable(f"Unable to extract media info: {exc}") from exc

        return DownloadResponse(post=post)

    async def stream_audio(
            self,
            url: str,
            format_id: str,
            title: str | None = None,
    ) -> StreamingResponse:
        """Resolve an audio format and relay its bytes to the browser.

        The upstream connection is opened *before* the response is created so
        that rate limits can still be retried with a proper HTTP status code.
        """
        service = self._get_service(url)
        resolved = await service.resolve_audio(url=url, format_id=format_id)
        source = await self._open_source(resolved.url)

        media_type = source.headers.get("Content-Type", "").split(";")[0].strip()
        # Prefer a known media type for the format we are about to serve, so
        # the browser always saves the file with a matching extension.
        if not media_type.startswith(("audio/", "video/")):
            media_type = _CONTENT_TYPES.get(resolved.ext, media_type or "application/octet-stream")

        headers: dict[str, str] = {
            "Content-Disposition": _content_disposition(
                f"{_safe_filename(title or 'audio')} [audio].{resolved.ext}"
            ),
        }
        # Passing the upstream length lets the browser show real progress.
        length = source.headers.get("Content-Length")
        if length:
            headers["Content-Length"] = length

        return StreamingResponse(
            self._relay(source),
            media_type=media_type,
            headers=headers,
        )

    async def stream_video(
            self,
            url: str,
            height: int,
            title: str | None = None,
    ) -> StreamingResponse:
        """Merge video with its audio track and stream the result as MP4.

        Falls back to direct download if ffmpeg merge fails (e.g. for platforms
        like Instagram where the video format may not be compatible with ffmpeg's
        -c copy merge mode).
        """
        service = self._get_service(url)
        streams = await service.resolve_streams(url=url, height=height)

        if shutil.which("ffmpeg") is None:
            raise MediaNotAvailable("ffmpeg is not installed on the server")

        filename = f"{_safe_filename(title or 'video')} [{streams.height}p].mp4"

        # Try ffmpeg merge first
        try:
            # Check ffmpeg return code before creating the response;
            # this ensures the exception propagates to the except block below.
            merged = self._merge_with_ffmpeg(streams)
            # Consume the generator to trigger ffmpeg execution and check return code
            async for _ in merged:
                pass
            # If we get here, ffmpeg succeeded - create the response
            return StreamingResponse(
                self._merge_with_ffmpeg(streams),
                media_type="video/mp4",
                headers={"Content-Disposition": _content_disposition(filename)},
            )
        except Exception:
            # Fallback: download the video directly via urllib
            # This handles platforms where ffmpeg -c copy merge mode is incompatible
            # (e.g. Instagram, Facebook, TikTok video formats).
            direct = await self._direct_download_video(streams, url)
            if direct is not None:
                return direct
            # If direct download also failed, re-raise the original error
            raise

    async def _direct_download_video(self, streams: ResolvedStreams, url: str | None = None) -> StreamingResponse | None:
        """Download video directly via urllib as fallback when ffmpeg merge fails.

        Tries the yt-dlp resolved video URL first, then falls back to the
        original platform URL if the resolved URL fails.

        Validates that the downloaded content is actually video (not HTML or
        other non-media content) before returning it to the client.
        """
        candidates = []
        if streams and streams.video_url:
            candidates.append(("resolved video URL", streams.video_url))
        if url:
            candidates.append(("original platform URL", url))

        for label, candidate_url in candidates:
            try:
                source = await self._open_source(candidate_url)
                content_type = source.headers.get("Content-Type", "").split(";")[0].strip()

                # Reject non-media content (HTML, error pages, etc.)
                if not content_type.startswith(("video/", "audio/")):
                    source.close()
                    logger.warning(
                        "_direct_download_video: %s returned non-media content-type: %s",
                        label, content_type,
                    )
                    continue

                # Read a small chunk to verify it's not HTML
                first_chunk = await asyncio.to_thread(source.read, 32)
                if first_chunk.startswith(b"<!DOCTYPE") or first_chunk.lstrip().startswith(b"<html"):
                    source.close()
                    logger.warning(
                        "_direct_download_video: %s returned HTML instead of video",
                        label,
                    )
                    continue

                # Re-wrap the source so we can replay the first chunk
                class _PrefixedSource:
                    def __init__(self, src, prefix):
                        self._src = src
                        self._prefix = prefix
                        self._prefix_sent = False

                    async def read(self, n):
                        if not self._prefix_sent:
                            self._prefix_sent = True
                            return self._prefix + (await asyncio.to_thread(self._src.read, max(0, n - len(self._prefix))))
                        return await asyncio.to_thread(self._src.read, n)

                    def close(self):
                        self._src.close()

                    @property
                    def headers(self):
                        return self._src.headers

                prefixed = _PrefixedSource(source, first_chunk)
                size_header = source.headers.get("Content-Length")
                size = int(size_header) if size_header and size_header.isdigit() else None

                headers: dict[str, str] = {
                    "Content-Disposition": _content_disposition(
                        f"{_safe_filename('video')} [{streams.height}p].mp4"
                    ),
                }
                if size:
                    headers["Content-Length"] = str(size)

                return StreamingResponse(
                    self._relay(prefixed),
                    media_type="video/mp4",
                    headers=headers,
                )
            except Exception as e:
                logger.debug("_direct_download_video: %s failed: %s", label, e)
                continue

        return None

    @staticmethod
    async def _open_source(url: str) -> Any:
        """Open the upstream media URL, retrying temporary rate limits.

        Returns:
            An open file-like object with readable ``headers``.

        Raises:
            MediaNotAvailable: When every attempt was refused by the host.
        """
        last_error: Exception | None = None

        for index, delay in enumerate((0.0, *_RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            # A ranged request is required: without `Range` the media host
            # throttles the stream to a few dozen kB/s, while `bytes=0-` is
            # answered at full speed and still reports the total size.
            headers = {"User-Agent": _USER_AGENT, "Range": "bytes=0-"}
            # Add Referer for media CDN hosts that require it
            for domain, referer in _CDN_REFERERS.items():
                if domain in url:
                    headers["Referer"] = referer
                    break
            request = urllib.request.Request(
                url,
                headers=headers,
            )
            try:
                return await asyncio.to_thread(
                    urllib.request.urlopen, request, timeout=60,
                )
            except urllib.error.HTTPError as exc:
                exc.close()
                last_error = exc
                if exc.code not in (403, 429):
                    raise MediaNotAvailable(f"Upstream host answered HTTP {exc.code}") from exc
                logger.warning(
                    "Rate limited by the media host (attempt %d): %s", index + 1, exc,
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "Cannot open the media host (attempt %d): %s", index + 1, exc,
                )

        raise MediaNotAvailable(f"Upstream host refused the media request: {last_error}")

    @staticmethod
    async def _relay(source: Any) -> AsyncIterator[bytes]:
        """Copy bytes from an already opened upstream response to the client."""
        try:
            while True:
                # Reads are blocking, so they run in a worker thread to keep
                # the event loop free for other requests.
                chunk = await asyncio.to_thread(source.read, _CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            # Runs on normal completion and when the client disconnects.
            source.close()

    @staticmethod
    async def _merge_with_ffmpeg(streams: ResolvedStreams) -> AsyncIterator[bytes]:
        """Run ffmpeg and yield the merged MP4 byte by byte.

        ``-c copy`` remuxes without re-encoding. A fragmented MP4 is required
        because a regular MP4 header can only be written once the whole file
        size is known, which never happens while streaming into a pipe.
        """
        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", streams.video_url,
        ]
        if streams.audio_url:
            # Separate DASH streams: video from the first input, audio from the second.
            args += ["-i", streams.audio_url, "-map", "0:v:0", "-map", "1:a:0?"]
        else:
            # Progressive stream: keep both tracks of the single input.
            args += ["-map", "0:v:0", "-map", "0:a:0?"]
        args += [
            "-c", "copy",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov",
            "pipe:1",
        ]

        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            # Do not flash a console window for every download on Windows.
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        # stderr is drained in the background, otherwise a full pipe buffer
        # would block ffmpeg while we are still reading stdout.
        stderr_task = asyncio.create_task(process.stderr.read())

        try:
            while True:
                chunk = await process.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

            returncode = await process.wait()
            stderr = (await stderr_task).decode(errors="replace").strip()
            if returncode != 0:
                raise MediaNotAvailable(f"ffmpeg exited with code {returncode}: {stderr}")
        finally:
            if process.returncode is None:
                # Client disconnected or the stream failed: stop ffmpeg.
                process.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=5)
            stderr_task.cancel()