from dishka import Provider, provide, Scope

from src.backend.download.service import DownloadService
from src.platforms.core.service import PlatformService
from src.platforms.facebook.service import FacebookService
from src.platforms.instagram.service import InstagramService
from src.platforms.tiktok.service import TikTokService
from src.platforms.youtube.service import YoutubeService


class DownloadProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_platform_services(
            self,
            youtube_service: YoutubeService,
            facebook_service: FacebookService,
            instagram_service: InstagramService,
            tiktok_service: TikTokService,
    ) -> list[PlatformService]:
        """Assemble all platform services into a dispatch list."""
        return [
            youtube_service,
            facebook_service,
            instagram_service,
            tiktok_service,
        ]

    @provide(scope=Scope.REQUEST)
    def get_download_service(
            self,
            services: list[PlatformService],
    ) -> DownloadService:
        return DownloadService(
            services=services
        )