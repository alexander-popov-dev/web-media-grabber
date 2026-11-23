"""Generic scraper for platforms other than YouTube.

Uses the shared base extraction logic without the YouTube-specific
``remote_components`` (which fetches ejs from GitHub and is unnecessary for
Facebook, Instagram, TikTok, etc.). Format selectors are the same
``height<=`` based ones that work across most yt-dlp-supported sites.
"""

from src.platforms.core.scraper import BaseScraper


class GenericScraper(BaseScraper):
    """Resolve media URLs for any platform supported by yt-dlp."""

    def __init__(self) -> None:
        # js_runtimes helps with signature challenges on many platforms;
        # remote_components is not needed for non-YouTube sites.
        super().__init__(use_js_runtimes=True, use_remote_components=False)
