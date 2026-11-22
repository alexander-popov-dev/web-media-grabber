"""YouTube extraction layer built on top of yt-dlp.

The scraper only talks to yt-dlp: it resolves post metadata and turns a
requested quality/format into direct media URLs that the backend is able to
stream. It never builds HTTP responses itself.
"""

import asyncio
import logging
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError

from src.platforms.core.schemas import ResolvedAudio, ResolvedStreams

logger = logging.getLogger(__name__)

# Options shared by every extraction call.
# `js_runtimes` and `remote_components` are mandatory: without them yt-dlp
# cannot solve the "n" signature challenge and silently drops several
# progressive formats from the result. `socket_timeout` keeps unreachable
# hosts from stalling a request for minutes.
_BASE_OPTS: dict[str, Any] = {
    "noplaylist": True,
    "skip_download": True,
    "js_runtimes": {"node": {}},
    "remote_components": ["ejs:github"],
    "socket_timeout": 15,
}

# Delay (seconds) before each retry. googlevideo rate-limits a client IP with
# HTTP 403/429 for a short while, and the very same URL starts working again
# after a couple of seconds, so retrying is cheaper than failing the request.
_RETRY_DELAYS = (1.0, 2.5, 5.0)


class YoutubeScraper:
    """Resolve YouTube posts into direct media URLs."""

    @staticmethod
    def _is_rate_limited(exc: BaseException) -> bool:
        """Return ``True`` when extraction failed with a temporary HTTP limit."""
        message = str(exc)
        return "HTTP Error 403" in message or "HTTP Error 429" in message

    async def _extract(self, url: str, fmt: str) -> dict[str, Any]:
        """Run yt-dlp format selection for ``url`` and return the info dict.

        yt-dlp is blocking, so the actual work is moved to a worker thread.
        Temporary rate limits are retried with a growing backoff.
        """
        opts = {**_BASE_OPTS, "format": fmt}
        last_error: Exception | None = None

        for index, delay in enumerate((0.0, *_RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # `download=False` still performs format selection but
                    # writes nothing to disk: only the resolved URLs are needed.
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            except Exception as exc:  # noqa: BLE001 - re-raised unless it is a rate limit
                last_error = exc
                if not self._is_rate_limited(exc):
                    raise
                logger.warning(
                    "Rate limited while resolving %s (attempt %d): %s",
                    url, index + 1, exc,
                )

        raise DownloadError(f"Unable to resolve {url}: {last_error}")

    @staticmethod
    def _has_video(fmt: dict[str, Any] | None) -> bool:
        """Check whether the format carries a video track and a media URL."""
        if not fmt or not fmt.get("url"):
            return False
        return fmt.get("vcodec") not in (None, "none")

    @staticmethod
    def _has_audio(fmt: dict[str, Any] | None) -> bool:
        """Check whether the format carries an audio track and a media URL."""
        if not fmt or not fmt.get("url"):
            return False
        return fmt.get("acodec") not in (None, "none")

    async def resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Resolve a single audio format to its direct media URL.

        Args:
            url: Page URL of the YouTube post.
            format_id: Exact yt-dlp format id (for example ``140`` or ``251``).

        Returns:
            Direct media URL, container extension and format name.

        Raises:
            DownloadError: When the format is missing or the host refuses us.
        """
        info = await self._extract(url=url, fmt=format_id)

        # A non merged (single) format selection puts the media URL on the top
        # level of the info dict instead of `requested_formats`.
        media_url = info.get("url")
        if not media_url:
            raise DownloadError(f"Format {format_id} is not available for {url}")

        return ResolvedAudio(
            url=media_url,
            ext=info.get("ext") or "m4a",
            format=info.get("format") or format_id,
        )

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve the best video stream for ``height`` together with its audio.

        YouTube serves DASH video without an audio track, so both URLs are
        returned and the backend stitches them together with ffmpeg.

        Args:
            url: Page URL of the YouTube post.
            height: Maximum video height (for example ``1080``).

        Returns:
            Video URL, optional audio URL and the resolved height.

        Raises:
            DownloadError: When no video stream matches the requested quality.
        """
        # `height<=` instead of `height=`: the exact height is not always
        # available, which would fail the whole request.
        fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        info = await self._extract(url=url, fmt=fmt)

        requested = info.get("requested_formats") or []
        if requested:
            video = next((f for f in requested if self._has_video(f)), None)
            audio = next((f for f in requested if self._has_audio(f)), None)
        else:
            # Progressive (single) format: one URL already carries both tracks.
            video = info if self._has_video(info) else None
            audio = info if self._has_audio(info) else None

        if not video:
            raise DownloadError(f"No video stream found for height <= {height} at {url}")

        return ResolvedStreams(
            video_url=video["url"],
            audio_url=audio.get("url") if audio else None,
            height=video.get("height") or height,
        )

    def download_video(self, url: str, height: int, out_dir: str = "downloads") -> None:
        """Download the best matching video+audio pair into ``out_dir``."""
        container = "mp4" if height <= 1080 else "mkv"
        opts = {
            "format": f"bv*[height={height}]+ba/b[height={height}]",
            "format_sort": ["ext"] if height <= 1080 else [],
            "merge_output_format": container,
            "outtmpl": f"{out_dir}/%(title).150B [{height}p].%(ext)s",
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    def download_audio(self, url: str, format_id: str, out_dir: str = "downloads") -> None:
        """Download a single audio format into ``out_dir``."""
        opts = {
            "format": format_id,
            "outtmpl": f"{out_dir}/%(title).150B [audio].%(ext)s",
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    @staticmethod
    async def get_post_info(url: str) -> dict:
        """Extract raw post metadata without downloading anything."""
        with yt_dlp.YoutubeDL(dict(_BASE_OPTS)) as ydl:
            result = await asyncio.to_thread(ydl.extract_info, url=url)
            return dict(result)
