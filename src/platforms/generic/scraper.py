"""Generic scraper for platforms other than YouTube.

Uses the shared base extraction logic without the YouTube-specific
``remote_components`` (which fetches ejs from GitHub and is unnecessary for
Facebook, Instagram, TikTok, etc.). Format selectors are the same
``height<=`` based ones that work across most yt-dlp-supported sites.
"""

from typing import Optional

from src.platforms.core.scraper import BaseScraper


class GenericScraper(BaseScraper):
    """Resolve media URLs for any platform supported by yt-dlp."""

    def __init__(
        self,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        auto_cookies_url: Optional[str] = None,
        auto_cookies_domain: Optional[str] = None,
        js_runtime: str | None = "node",
    ) -> None:
        # js_runtime helps with signature challenges on many platforms;
        # remote_components is not needed for non-YouTube sites.
        super().__init__(
            js_runtime=js_runtime,
            use_remote_components=False,
            cookies_from_browser=cookies_from_browser,
            cookies_file=cookies_file,
            auto_cookies_url=auto_cookies_url,
            auto_cookies_domain=auto_cookies_domain,
        )
