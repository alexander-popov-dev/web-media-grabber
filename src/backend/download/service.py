"""Streaming logic of the download layer.

The service turns resolved platform links into HTTP streams: audio bytes are
relayed from the upstream host, while video is stitched on the fly with ffmpeg
and pushed to the client as a fragmented MP4.
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
from src.platforms.youtube.service import YoutubeService

logger = logging.getLogger(__name__)

# Size of a single chunk pushed to the client.
_CHUNK_SIZE = 64 * 1024

# Browser-like user agent: the media host occasionally rejects unknown clients.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

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
            youtube_service: YoutubeService
    ) -> None:
        self._youtube_service = youtube_service

    async def get_download_url(self, request: DownloadRequest) -> DownloadResponse:
        """Fetch and parse metadata of the given post.

        Raises:
            PlatformNotSupported: When the URL does not belong to a platform
                this server knows how to handle.
            MediaNotAvailable: When the upstream host cannot be extracted.
        """
        self._ensure_supported(request.url)

        try:
            post = await self._youtube_service.get_post_info(url=request.url)
        except Exception as exc:  # noqa: BLE001 - reported to the client as a 5xx
            raise MediaNotAvailable(f"Unable to extract media info: {exc}") from exc

        return DownloadResponse(post=post)

    def _ensure_supported(self, url: str) -> None:
        """Reject URLs that do not belong to a platform this server supports.

        Raises:
            PlatformNotSupported: When no known platform marker is present.
        """
        if self._youtube_service.PLATFORM not in url:
            raise PlatformNotSupported(f"Unsupported platform for url: {url}")

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
        self._ensure_supported(url)
        resolved = await self._resolve_audio(url=url, format_id=format_id)
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
        """Merge video with its audio track and stream the result as MP4."""
        self._ensure_supported(url)
        streams = await self._resolve_streams(url=url, height=height)

        if shutil.which("ffmpeg") is None:
            raise MediaNotAvailable("ffmpeg is not installed on the server")

        filename = f"{_safe_filename(title or 'video')} [{streams.height}p].mp4"
        return StreamingResponse(
            self._merge_with_ffmpeg(streams),
            media_type="video/mp4",
            headers={"Content-Disposition": _content_disposition(filename)},
        )

    async def _resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Ask the platform layer for a direct audio URL."""
        try:
            return await self._youtube_service.resolve_audio(url=url, format_id=format_id)
        except Exception as exc:  # noqa: BLE001 - reported to the client as a 5xx
            raise MediaNotAvailable(f"Unable to resolve audio format: {exc}") from exc

    async def _resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Ask the platform layer for the video/audio pair of a quality."""
        try:
            return await self._youtube_service.resolve_streams(url=url, height=height)
        except Exception as exc:  # noqa: BLE001 - reported to the client as a 5xx
            raise MediaNotAvailable(f"Unable to resolve video format: {exc}") from exc

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
            request = urllib.request.Request(
                url,
                headers={"User-Agent": _USER_AGENT, "Range": "bytes=0-"},
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
                # Headers are already sent, so the failure can only be logged.
                logger.error("ffmpeg exited with code %d: %s", returncode, stderr)
        finally:
            if process.returncode is None:
                # Client disconnected or the stream failed: stop ffmpeg.
                process.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=5)
            stderr_task.cancel()
