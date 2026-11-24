from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.facebook.service import FacebookService
from src.platforms.generic.scraper import GenericScraper


class FacebookProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        # Support cookies from browser for authenticated requests (Facebook Reels, etc.)
        # Set FB_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        import os
        cookies_browser = os.getenv("FB_COOKIES_BROWSER")
        return GenericScraper(cookies_from_browser=cookies_browser)

    @provide(scope=Scope.REQUEST)
    def get_facebook_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> FacebookService:
        return FacebookService(scraper=scraper, parser=parser)
