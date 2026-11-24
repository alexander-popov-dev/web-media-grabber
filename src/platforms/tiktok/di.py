from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.tiktok.service import TikTokService


class TikTokProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        # Support cookies from browser for authenticated requests (TikTok, etc.)
        # Set TT_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        import os
        cookies_browser = os.getenv("TT_COOKIES_BROWSER")
        return GenericScraper(cookies_from_browser=cookies_browser)

    @provide(scope=Scope.REQUEST)
    def get_tiktok_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> TikTokService:
        return TikTokService(scraper=scraper, parser=parser)
