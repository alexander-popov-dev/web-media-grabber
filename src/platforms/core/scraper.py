"""Base scraper for all platforms.

Provides the shared yt-dlp extraction logic: ``js_runtimes``/``remote_components``
configuration, retry/backoff on temporary HTTP 403/429 rate limits, and socket
timeouts so unreachable hosts do not stall requests for minutes.
"""

import asyncio
import logging
import os
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)

# Delay (seconds) before each retry. googlevideo and other media hosts rate-limit
# a client IP with HTTP 403/429 for a short while; the same URL usually starts
# working again after a couple of seconds, so retrying is cheaper than failing.
_RETRY_DELAYS = (1.0, 2.5, 5.0)


class BaseScraper:
    """Run yt-dlp format selection for a URL and return the resolved info dict.

    Parameters
    ----------
    use_js_runtimes:
        Enable the JavaScript runtime for solving YouTube's signature challenge.
        Required for YouTube; harmless but unnecessary for most other platforms.
    use_remote_components:
        Load remote yt-dlp components (e.g. ``ejs:github``). Required for
        YouTube to keep progressive formats; disabled by default for other
        platforms to avoid an extra network hop to GitHub.
    cookies_from_browser:
        Browser name to extract cookies from (e.g., "chrome", "firefox", "edge").
        Used for authenticated requests (YouTube Shorts, Facebook Reels, etc.).
    cookies_file:
        Path to cookies file in Netscape format (e.g., /app/cookies.txt).
        Used when no browser is available (containers).
    """

    def __init__(
        self,
        use_js_runtimes: bool = True,
        use_remote_components: bool = False,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ) -> None:
        self._use_js_runtimes = use_js_runtimes
        self._use_remote_components = use_remote_components
        self._cookies_from_browser = cookies_from_browser
        self._cookies_file = cookies_file or os.getenv("YTDLP_COOKIES_FILE")

    @property
    def _base_opts(self) -> dict[str, Any]:
        """Build yt-dlp options shared by every extraction call."""
        opts: dict[str, Any] = {
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 15,
        }
        if self._use_js_runtimes:
            # Use deno for JavaScript runtime (recommended by yt-dlp)
            opts["js_runtimes"] = {"deno": {}}
        if self._use_remote_components:
            opts["remote_components"] = ["ejs:github"]
        if self._cookies_from_browser:
            opts["cookies_from_browser"] = self._cookies_from_browser
        if self._cookies_file:
            opts["cookiefile"] = self._cookies_file
        return opts