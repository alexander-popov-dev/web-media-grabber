from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.tiktok.service import TikTokService


class TikTokProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        # Support cookies from browser for authenticated requests (TikTok, etc.)
        # Set TT_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        # Or use YTDLP_COOKIES_FILE for cookie file in containers
        import os
        cookies_browser = os.getenv("TT_COOKIES_BROWSER")
        cookies_file = os.getenv("YTDLP_COOKIES_FILE") or "/app/cookies_tiktok.txt"
        return GenericScraper(
            cookies_from_browser=cookies_browser,
            cookies_file=cookies_file,
        )

    @provide(scope=Scope.REQUEST)
    def get_tiktok_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> TikTokService:
        return TikTokService(scraper=scraper, parser=parser)