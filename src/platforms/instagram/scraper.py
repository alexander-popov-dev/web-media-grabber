import logging

from src.core.client import request, PlatformConfig

logger = logging.getLogger(__name__)


class InstagramScraper:
    """Resolve Instagram posts into direct media URLs."""

    def __init__(self, config: PlatformConfig):
        self._config = config

    async def get_post_info(self, url: str) -> dict:
        """Extract raw post metadata without downloading anything."""
        return await request(
            method="GET",
            url=url,
            config=self._config,
        )
