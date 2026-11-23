from dishka import AsyncContainer, make_async_container

from src.backend.download.di import DownloadProvider
from src.platforms.facebook.di import FacebookProvider
from src.platforms.generic.di import GenericProvider
from src.platforms.instagram.di import InstagramProvider
from src.platforms.tiktok.di import TikTokProvider
from src.platforms.youtube.di import YoutubeProvider


def get_container() -> AsyncContainer:
    return make_async_container(
        DownloadProvider(),
        YoutubeProvider(),
        GenericProvider(),
        FacebookProvider(),
        InstagramProvider(),
        TikTokProvider(),
    )
