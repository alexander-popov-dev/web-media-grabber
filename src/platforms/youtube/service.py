from src.platforms.youtube.parser import YoutubeParser
from src.platforms.core.schemas import Post
from src.platforms.youtube.scraper import YoutubeScraper


class YoutubeService:
    PLATFORM = "youtube"

    def __init__(
            self,
            scraper: YoutubeScraper,
            parser: YoutubeParser
    ) -> None:
        self._scraper = scraper
        self._parser = parser

    async def get_post_info(self, url: str) -> Post:
        response = await self._scraper.get_post_info(url=url)
        return self._parser.parse(response=response)
