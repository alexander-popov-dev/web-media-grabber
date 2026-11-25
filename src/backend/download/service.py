"""Streaming logic of the download layer.

Every download is performed by the platform scraper's yt-dlp context so that
cookies, PO tokens and signed media URLs stay consistent. The legacy
resolve-then-relay fallback was removed: fetching the resolved URLs with a
bare urllib/ffmpeg request reliably gets HTTP 403 from YouTube and only
doubles the number of upstream requests.
"""

import asyncio
import contextlib
import logging
import re
import shutil
import tempfile
import urllib.parse
from collections.abc import AsyncIterator
from pathlib import Path

from starlette.responses import StreamingResponse

from src.backend.download.exceptions import MediaNotAvailable, PlatformNotSupported
from src.backend.download.schemas import DownloadResponse
from src.platforms.core.service import PlatformService

logger = logging.getLogger(__name__)

# Size of a single chunk pushed to the client. Large chunks avoid a thread hop
# per 64 KiB on every streamed file.
_CHUNK_SIZE = 256 * 1024

# Hostname suffixes used to dispatch a URL to the right platform service.
_PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "facebook": ("facebook.com", "fb.watch"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
}

# Errors that mean "stop trying other selectors": the host is blocking us,
# not merely missing the requested format.
_BLOCKING_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "http error 403",
    "http error 429",
    "unable to download video data",
)

_AUDIO_CONTENT_TYPES = {
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "mp3": "audio/mpeg",
    "aac": "audio/aac",
}

_VIDEO_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(value: str, fallback: str = "media") -> str:
    """Strip characters that are illegal in file names and cap the length."""
    cleaned = _INVALID_FILENAME_CHARS.sub("", value or "").strip().strip(".")
    return cleaned[:150] or fallback


def _content_disposition(filename: str) -> str:
    """Build a ``Content-Disposition`` header safe for non-ASCII titles."""
    fallback = filename.encode("ascii", "ignore").decode()
    fallback = re.sub(r"\s+", " ", fallback).strip() or "media"
    encoded = urllib.parse.quote(filename, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


def _is_blocking_error(exc: BaseException) -> bool:
    """Return True when another selector would hit the same upstream block."""
    message = str(exc).lower()
    return any(marker in message for marker in _BLOCKING_MARKERS)


class DownloadService:
    """Turns platform URLs into files streamed back to the browser."""

    def __init__(self, services: list[PlatformService]) -> None:
        self._services = {service.PLATFORM: service for service in services}

    def _get_service(self, url: str) -> PlatformService:
        """Pick the platform service matching the URL hostname."""
        host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
        if host:
            for platform, service in self._services.items():
                suffixes = _PLATFORM_HOSTS.get(platform, (platform,))
                if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
                    return service
        else:
            # Malformed/scheme-less URL: keep the old best-effort behaviour.
            lowered = url.lower()
            for platform, service in self._services.items():
                if platform in lowered:
                    return service
        raise PlatformNotSupported(f"Unsupported platform for url: {url}")

    async def get_download_url(self, url: str) -> DownloadResponse:
        """Fetch and parse metadata of the given post."""
        service = self._get_service(url)
        try:
            post = await service.get_post_info(url=url)
        except Exception as exc:  # noqa: BLE001 - reported to the client as a 5xx
            raise MediaNotAvailable(f"Unable to extract media info: {exc}") from exc
        return DownloadResponse(post=post)

    async def stream_audio(
        self,
        url: str,
        format_id: str,
        title: str | None = None,
    ) -> StreamingResponse:
        """Download a single audio format and stream it to the browser."""
        service = self._get_service(url)
        return await self._download_with_ytdlp(
            url, title or "audio", service=service, format_id=format_id
        )

    async def stream_video(
        self,
        url: str,
        height: int,
        title: str | None = None,
    ) -> StreamingResponse:
        """Download the requested video quality and stream it as MP4."""
        service = self._get_service(url)
        return await self._download_with_ytdlp(
            url, title or "video", service=service, height=height
        )

    async def _download_with_ytdlp(
        self,
        url: str,
        title: str,
        *,
        service: PlatformService,
        height: int | None = None,
        format_id: str | None = None,
    ) -> StreamingResponse:
        """Download with the platform scraper's exact yt-dlp options."""
        if format_id:
            # A stored format id may disappear when YouTube changes its player
            # clients; `bestaudio` keeps audio downloads usable in that case.
            selectors = [format_id]
            if format_id not in ("bestaudio", "ba"):
                selectors.append("bestaudio")
            label = "audio"
            merge_output_format = None
            content_types = _AUDIO_CONTENT_TYPES
        else:
            # Prefer separate video+audio, then a progressive format, then the
            # best available fallback (often an HLS stream).
            selectors = [
                f"bv*[height<={height}]+ba/b[height<={height}]",
                f"b[height<={height}]",
                "best",
            ]
            label = f"{height}p"
            merge_output_format = "mp4"
            content_types = _VIDEO_CONTENT_TYPES

        last_error: Exception | None = None
        for selector in selectors:
            out_dir = tempfile.mkdtemp(prefix="mediadl_")
            try:
                path = await service.download_to_file(
                    url,
                    format_selector=selector,
                    out_dir=out_dir,
                    filename="%(id)s.%(ext)s",
                    merge_output_format=merge_output_format,
                )
                size = path.stat().st_size
                ext = path.suffix.lstrip(".").lower() or "mp4"
                media_type = content_types.get(
                    ext, "application/octet-stream" if format_id else "video/mp4"
                )
                headers = {
                    "Content-Disposition": _content_disposition(
                        f"{_safe_filename(title)} [{label}].{ext}"
                    ),
                }
                if size:
                    headers["Content-Length"] = str(size)
                return StreamingResponse(
                    self._stream_temp_file(path, out_dir),
                    media_type=media_type,
                    headers=headers,
                )
            except Exception as exc:  # noqa: BLE001 - try the next selector
                last_error = exc
                logger.warning("yt-dlp selector %s failed for %s: %s", selector, url, exc)
                shutil.rmtree(out_dir, ignore_errors=True)
                if _is_blocking_error(exc):
                    break

        kind = "audio" if format_id else "video"
        raise MediaNotAvailable(
            f"Unable to download this {kind}. The media host may be blocking "
            "the request or the format may not be supported."
        ) from last_error

    @staticmethod
    async def _stream_temp_file(path: Path, out_dir: str) -> AsyncIterator[bytes]:
        """Relay a downloaded file to the client and remove it afterwards."""
        try:
            with path.open("rb") as source:
                while True:
                    chunk = await asyncio.to_thread(source.read, _CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
        finally:
            with contextlib.suppress(OSError):
                path.unlink()
            shutil.rmtree(out_dir, ignore_errors=True)
