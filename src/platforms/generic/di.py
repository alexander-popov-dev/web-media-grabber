from dishka import Provider, provide, Scope

from src.backend.settings import get_backend_settings
from src.platforms.core.parser import BaseParser
from src.platforms.facebook.service import FacebookService
from src.platforms.generic.scraper import GenericScraper
from src.platforms.instagram.service import InstagramService
from src.platforms.tiktok.service import TikTokService

backend_settings = get_backend_settings()


class GenericProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_scraper(self) -> GenericScraper:
        return GenericScraper()

    @provide(scope=Scope.REQUEST)
    def get_parser(self) -> BaseParser:
        return BaseParser(
            base_url=f"{backend_settings.get_base_url}/api/post",
        )

    @provide(scope=Scope.REQUEST)
    def get_facebook_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> "FacebookService":
        from src.platforms.facebook.service import FacebookService
        return FacebookService(scraper=scraper, parser=parser)

    @provide(scope=Scope.REQUEST)
    def get_instagram_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> "InstagramService":
        from src.platforms.instagram.service import InstagramService
        return InstagramService(scraper=scraper, parser=parser)

    @provide(scope=Scope.REQUEST)
    def get_tiktok_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> "TikTokService":
        from src.platforms.tiktok.service import TikTokService
        return TikTokService(scraper=scraper, parser=parser)
