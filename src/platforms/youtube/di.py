from dishka import Provider, provide, Scope

from src.backend.settings import get_backend_settings
from src.platforms.youtube.parser import YoutubeParser
from src.platforms.youtube.scraper import YoutubeScraper
from src.platforms.youtube.service import YoutubeService

backend_settings = get_backend_settings()


class YoutubeProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> YoutubeScraper:
        # Support cookies from browser for authenticated requests (YouTube Shorts, etc.)
        # Set YT_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        # Or use YTDLP_COOKIES_FILE for cookie file in containers
        import os
        cookies_browser = os.getenv("YT_COOKIES_BROWSER")
        cookies_file = os.getenv("YTDLP_COOKIES_FILE")
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