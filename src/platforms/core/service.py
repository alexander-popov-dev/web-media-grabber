"""Abstract platform service interface.

Every platform integration (YouTube, Facebook, Instagram, TikTok, …)
implements this interface so the download layer can dispatch requests
without knowing the concrete platform.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.platforms.core.schemas import Post, ResolvedAudio, ResolvedStreams


@runtime_checkable
class PlatformService(Protocol):
    """Protocol every platform service must satisfy."""

    PLATFORM: str

    async def get_post_info(self, url: str) -> Post:
        """Extract and parse post metadata: title, author, formats, sizes."""

    async def resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Resolve a single audio format to its direct media URL."""

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve a video quality to the video/audio URLs to merge."""

    async def download_to_file(
        self,
        url: str,
        *,
        format_selector: str,
        out_dir: str,
        filename: str = "%(id)s.%(ext)s",
        merge_output_format: str | None = None,
    ) -> Path:
        """Download a format through the platform's yt-dlp context."""


class BasePlatformService:
    """Base implementation of :class:`PlatformService`.

    Delegates to a scraper (yt-dlp) and a parser (raw info -> Post schema).
    Subclasses only set ``PLATFORM`` and inject the right scraper/parser.
    """

    PLATFORM: str = ""

    def __init__(self, scraper: Any, parser: Any) -> None:
        self._scraper = scraper
        self._parser = parser

    async def get_post_info(self, url: str) -> Post:
        """Extract raw info from yt-dlp and parse it into a ``Post``."""
        response = await self._scraper.get_post_info(url=url)
        return self._parser.parse(response=response)

    async def resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Resolve a single audio format to its direct media URL."""
        result = await self._scraper.resolve_audio(url=url, format_id=format_id)
        # The scraper may return a raw dict (e.g. GenericScraper); convert to typed object.
        if isinstance(result, dict):
            return ResolvedAudio(
                url=result.get("url", ""),
                ext=result.get("ext", "m4a"),
                format=result.get("format") or format_id,
            )
        return result

    async def download_to_file(
        self,
        url: str,
        *,
        format_selector: str,
        out_dir: str,
        filename: str = "%(id)s.%(ext)s",
        merge_output_format: str | None = None,
    ) -> Path:
        """Download a format into ``out_dir`` using the platform scraper."""
        return await self._scraper.download_to_file(
            url,
            format_selector=format_selector,
            out_dir=out_dir,
            filename=filename,
            merge_output_format=merge_output_format,
        )

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve a video quality to the video/audio URLs to merge."""
        result = await self._scraper.resolve_streams(url=url, height=height)
        # The scraper may return a raw dict; convert to typed object.
        if isinstance(result, dict):
            # For DASH streams (Instagram, Facebook, TikTok), the top-level
            # ``url`` is often ``None``. The actual video/audio URLs live inside
            # ``requested_formats``.
            video_url = result.get("video_url") or result.get("url") or ""
            audio_url = result.get("audio_url")
            if not video_url and "requested_formats" in result:
                for f in result["requested_formats"]:
                    if f.get("vcodec") != "none" and f.get("acodec") == "none":
                        video_url = f.get("url", "")
                        break
            if not audio_url and "requested_formats" in result:
                for f in result["requested_formats"]:
                    if f.get("acodec") != "none" and f.get("vcodec") == "none":
                        audio_url = f.get("url")
                        break
            return ResolvedStreams(
                video_url=video_url,
                audio_url=audio_url,
                height=result.get("height") or height,
            )
        return result
