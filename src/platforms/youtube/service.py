from src.platforms.core.schemas import Post, ResolvedAudio, ResolvedStreams
from src.platforms.youtube.parser import YoutubeParser
from src.platforms.youtube.scraper import YoutubeScraper


class YoutubeService:
    """Application-facing YouTube facade: extraction plus parsing."""

    PLATFORM = "youtube"

    def __init__(
            self,
            scraper: YoutubeScraper,
            parser: YoutubeParser
    ) -> None:
        self._scraper = scraper
        self._parser = parser

    async def get_post_info(self, url: str) -> Post:
        """Return parsed post metadata (title, formats, sizes)."""
        response = await self._scraper.get_post_info(url=url)
        return self._parser.parse(response=response)

    async def resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Resolve an audio format id into a direct media URL."""
        return await self._scraper.resolve_audio(url=url, format_id=format_id)

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve a video quality into the video/audio URLs to merge."""
        return await self._scraper.resolve_streams(url=url, height=height)
