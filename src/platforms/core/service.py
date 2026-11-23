"""Abstract platform service interface.

Every platform integration (YouTube, Facebook, Instagram, TikTok, …)
implements this interface so the download layer can dispatch requests
without knowing the concrete platform.
"""

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
        return await self._scraper.resolve_audio(url=url, format_id=format_id)

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve a video quality to the video/audio URLs to merge."""
        return await self._scraper.resolve_streams(url=url, height=height)
