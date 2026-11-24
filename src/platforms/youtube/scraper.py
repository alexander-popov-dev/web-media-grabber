"""YouTube extraction layer built on top of the shared base scraper.

Adds YouTube-specific format selectors and the ``js_runtimes`` +
``remote_components`` options that are mandatory for YouTube (without them
yt-dlp cannot solve the signature challenge and silently drops several
progressive formats).
"""

import logging
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from src.platforms.core.scraper import BaseScraper
from src.platforms.core.schemas import ResolvedAudio, ResolvedStreams

logger = logging.getLogger(__name__)


class YoutubeScraper(BaseScraper):
    """Resolve YouTube posts into direct media URLs."""

    def __init__(self, cookies_from_browser: Optional[str] = None, cookies_file: Optional[str] = None) -> None:
        # YouTube needs both js_runtimes (signature challenge) and
        # remote_components (ejs from github, keeps progressive formats).
        super().__init__(
            use_js_runtimes=True,
            use_remote_components=True,
            cookies_from_browser=cookies_from_browser,
            cookies_file=cookies_file,
        )

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

        # A non-merged (single) format selection puts the media URL on the top
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
        info = await super().resolve_streams(url=url, height=height)

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