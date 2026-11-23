from src.platforms.core.parser import BaseParser
from src.platforms.core.service import BasePlatformService
from src.platforms.core.schemas import Post, ResolvedAudio, ResolvedStreams
from src.platforms.generic.scraper import GenericScraper


class FacebookService(BasePlatformService):
    """Facebook platform facade delegating to GenericScraper + BaseParser."""

    PLATFORM = "facebook"

    def __init__(self, scraper: GenericScraper, parser: BaseParser) -> None:
        super().__init__(scraper=scraper, parser=parser)

    async def get_post_info(self, url: str) -> Post:
        """Return parsed post metadata: title, thumbnail, formats, sizes."""
        return await super().get_post_info(url=url)

    async def resolve_audio(self, url: str, format_id: str) -> ResolvedAudio:
        """Resolve an audio format id into a direct media URL."""
        return await super().resolve_audio(url=url, format_id=format_id)

    async def resolve_streams(self, url: str, height: int) -> ResolvedStreams:
        """Resolve a video quality into the video/audio URLs to merge."""
        return await super().resolve_streams(url=url, height=height)
