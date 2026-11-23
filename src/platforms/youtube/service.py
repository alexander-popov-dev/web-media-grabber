from src.platforms.core.parser import BaseParser
from src.platforms.core.service import BasePlatformService
from src.platforms.core.schemas import Post
from src.platforms.youtube.parser import YoutubeParser
from src.platforms.youtube.scraper import YoutubeScraper


class YoutubeService(BasePlatformService):
    """YouTube application-facing facade: extraction plus parsing."""

    PLATFORM = "youtube"

    def __init__(
            self,
            scraper: YoutubeScraper,
            parser: YoutubeParser
    ) -> None:
        super().__init__(scraper=scraper, parser=parser)

    async def get_post_info(self, url: str) -> Post:
        """Return parsed post metadata (title, thumbnail and media formats)."""
        return await super().get_post_info(url=url)

    async def resolve_audio(self, url: str, format_id: str):
        """Resolve an audio format id into a direct media URL."""
        return await super().resolve_audio(url=url, format_id=format_id)

    async def resolve_streams(self, url: str, height: int):
        """Resolve a video quality into the video/audio URLs to merge."""
        return await super().resolve_streams(url=url, height=height)
