import logging
import os

from dishka import Provider, provide, Scope

from src.backend.settings import get_backend_settings
from src.platforms.youtube.parser import YoutubeParser
from src.platforms.youtube.scraper import YoutubeScraper
from src.platforms.youtube.service import YoutubeService

backend_settings = get_backend_settings()
logger = logging.getLogger(__name__)


class YoutubeProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> YoutubeScraper:
        # Use bind mount cookies file (has auth cookies like __Secure-YNID)
        cookies_browser = os.getenv("YT_COOKIES_BROWSER")
        cookies_file = os.getenv("YT_COOKIES_FILE") or "/app/cookies/cookies_youtube.txt"
        
        logger.info("YouTube scraper: cookies_browser=%s, cookies_file=%s", cookies_browser, cookies_file)
        
        return YoutubeScraper(
            cookies_from_browser=cookies_browser,
            cookies_file=cookies_file,
        )

    @provide(scope=Scope.REQUEST)
    def get_parser(self) -> YoutubeParser:
        # The parser appends `/download`, so the base URL must point at the
        # download router prefix (`/api/post`) instead of the service root.
        return YoutubeParser(base_url=f"{backend_settings.get_base_url}/api/post")

    @provide(scope=Scope.REQUEST)
    def get_service(
            self,
            scraper: YoutubeScraper,
            parser: YoutubeParser,
    ) -> YoutubeService:
        return YoutubeService(
            scraper=scraper,
            parser=parser,
        )