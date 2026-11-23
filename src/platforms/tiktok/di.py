from dishka import Provider, provide, Scope

from src.platforms.core.parser import BaseParser
from src.platforms.generic.scraper import GenericScraper
from src.platforms.tiktok.service import TikTokService


class TikTokProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_tiktok_service(
            self,
            scraper: GenericScraper,
            parser: BaseParser,
    ) -> TikTokService:
        return TikTokService(scraper=scraper, parser=parser)
