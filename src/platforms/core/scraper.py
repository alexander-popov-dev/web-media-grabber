"""Base scraper for all platforms.

Provides the shared yt-dlp extraction logic: ``js_runtimes``/``remote_components``
configuration, retry/backoff on temporary HTTP 403/429 rate limits, and socket
timeouts so unreachable hosts do not stall requests for minutes.
"""

import asyncio
import logging
from typing import Any

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
        Enable the Node.js runtime for solving YouTube's signature challenge.
        Required for YouTube; harmless but unnecessary for most other platforms.
    use_remote_components:
        Load remote yt-dlp components (e.g. ``ejs:github``). Required for
        YouTube to keep progressive formats; disabled by default for other
        platforms to avoid an extra network hop to GitHub.
    """

    def __init__(
        self,
        use_js_runtimes: bool = True,
        use_remote_components: bool = False,
    ) -> None:
        self._use_js_runtimes = use_js_runtimes
        self._use_remote_components = use_remote_components

    @property
    def _base_opts(self) -> dict[str, Any]:
        """Build yt-dlp options shared by every extraction call."""
        opts: dict[str, Any] = {
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 15,
        }
        if self._use_js_runtimes:
            opts["js_runtimes"] = {"node": {}}
        if self._use_remote_components:
            opts["remote_components"] = ["ejs:github"]
        return opts

    @staticmethod
    def _is_rate_limited(exc: BaseException) -> bool:
        """Return ``True`` when extraction failed with a temporary HTTP limit."""
        message = str(exc)
        return "HTTP Error 403" in message or "HTTP Error 429" in message

    async def _extract(self, url: str, fmt: str) -> dict[str, Any]:
        """Run yt-dlp format selection for ``url`` and return the info dict.

        yt-dlp is blocking, so the actual work moves to a worker thread.
        Temporary rate limits are retried with a growing backoff.
        """
        opts = {**self._base_opts, "format": fmt}
        last_error: Exception | None = None

        for index, delay in enumerate((0.0, *_RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # `download=False` still performs format selection but
                    # writes nothing to disk: only the resolved URLs are needed.
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            except Exception as exc:  # noqa: BLE001 - re-raised unless it is a rate limit
                last_error = exc
                if not self._is_rate_limited(exc):
                    raise
                logger.warning(
                    "Rate limited while resolving %s (attempt %d): %s",
                    url, index + 1, exc,
                )

        raise DownloadError(f"Unable to resolve {url}: {last_error}")

    async def resolve_audio(self, url: str, format_id: str) -> dict[str, Any]:
        """Resolve a single audio format to its direct media URL.

        Returns the raw yt-dlp info dict for the selected format. Platform
        services are expected to wrap this into :class:`ResolvedAudio`.
        """
        info = await self._extract(url=url, fmt=format_id)
        media_url = info.get("url")
        if not media_url:
            raise DownloadError(f"Format {format_id} is not available for {url}")
        return info

    async def resolve_streams(self, url: str, height: int) -> dict[str, Any]:
        """Resolve the best video stream for ``height`` together with its audio.

        Returns the raw yt-dlp info dict. Platform services wrap this into
        :class:`ResolvedStreams`.
        """
        # `height<=` instead of `height=`: the exact height is not always
        # available, which would fail the whole request.
        fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        return await self._extract(url=url, fmt=fmt)

    async def get_post_info(self, url: str) -> dict:
        """Extract raw post metadata without downloading anything."""
        with yt_dlp.YoutubeDL(dict(self._base_opts)) as ydl:
            result = await asyncio.to_thread(ydl.extract_info, url=url)
            return dict(result)
