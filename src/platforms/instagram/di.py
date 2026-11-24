from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.instagram.service import InstagramService


class InstagramProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        # Support cookies from browser for authenticated requests (Instagram Reels, etc.)
        # Set IG_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        import os
        cookies_browser = os.getenv("IG_COOKIES_BROWSER")
        return GenericScraper(cookies_from_browser=cookies_browser)

    @provide(scope=Scope.REQUEST)
    def get_instagram_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> InstagramService:
        return InstagramService(scraper=scraper, parser=parser)
