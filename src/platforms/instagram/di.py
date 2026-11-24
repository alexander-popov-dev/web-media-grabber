from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.instagram.service import InstagramService


class InstagramProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        # Support cookies from browser for authenticated requests (Instagram Reels, etc.)
        # Set IG_COOKIES_BROWSER=chrome/firefox/edge in .env to enable
        # Or use IG_COOKIES_FILE for cookie file in containers
        import os
        cookies_browser = os.getenv("IG_COOKIES_BROWSER")
        cookies_file = os.getenv("IG_COOKIES_FILE") or "/app/cookies/cookies_instagram.txt"
        return GenericScraper(
            cookies_from_browser=cookies_browser,
            cookies_file=cookies_file,
        )

    @provide(scope=Scope.REQUEST)
    def get_instagram_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> InstagramService:
        return InstagramService(scraper=scraper, parser=parser)