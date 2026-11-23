from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.facebook.service import FacebookService
from src.platforms.generic.scraper import GenericScraper


class FacebookProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_facebook_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> FacebookService:
        return FacebookService(scraper=scraper, parser=parser)
