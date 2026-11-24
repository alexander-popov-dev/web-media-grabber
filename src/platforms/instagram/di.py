from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.instagram.service import InstagramService


class InstagramProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_instagram_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> InstagramService:
        return InstagramService(scraper=scraper, parser=parser)
