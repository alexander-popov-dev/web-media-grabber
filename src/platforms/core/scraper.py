"""Base scraper for all platforms.

Provides the shared yt-dlp extraction logic: ``js_runtimes``/``remote_components``
configuration, retry/backoff on temporary HTTP 403/429 rate limits, and socket
timeouts so unreachable hosts do not stall requests for minutes.
"""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)

# Delay (seconds) before each retry. googlevideo and other media hosts rate-limit
# a client IP with HTTP 403/429 for a short while; the same URL usually starts
# working again after a couple of seconds, so retrying is cheaper than failing.
_RETRY_DELAYS = (1.0, 2.5, 5.0)


def _configured_proxy() -> str | None:
    """Return the explicit outbound proxy for YouTube requests, if any.

    YouTube can flag a server IP for bot checks; neither cookies nor player
    clients bypass that, so the only reliable fix is routing via another IP.
    Standard ``HTTPS_PROXY`` is already honoured by yt-dlp, but an explicit
    variable makes the intent unambiguous in Docker.
    """
    return os.getenv("YOUTUBE_PROXY") or os.getenv("YTDLP_PROXY") or None


def _read_cookies_file(filepath: str) -> str | None:
    """Read a cookie file once and validate its shape.

    Accepts either a full Netscape file or a raw ``name=value; ...`` header.
    Mixed formats are rejected instead of being silently passed to yt-dlp.
    """
    try:
        content = Path(filepath).read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not content:
        return None

    lines = [line for line in content.splitlines() if line and not line.startswith("#")]
    if not lines:
        return None
    if all(len(line.split("\t")) == 7 for line in lines):
        return content
    if "\t" not in content and "=" in content and ";" in content:
        return content
    return None


def _normalize_cookies_content(content: str, domain: str = "youtube.com") -> str:
    """Convert a raw cookie header to Netscape format on the fly."""
    lines = [line for line in content.splitlines() if line and not line.startswith("#")]
    if lines and all(len(line.split("\t")) == 7 for line in lines):
        logger.debug("cookies already in Netscape format: %d lines", len(lines))
        return content

    pairs: list[tuple[str, str]] = []
    for part in content.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            pairs.append((name.strip(), value.strip()))

    if not pairs:
        logger.warning("no cookie pairs parsed; passing file through to yt-dlp")
        return content

    logger.debug("parsed %d cookie pairs", len(pairs))
    # A fixed past date makes yt-dlp discard every cookie as expired, so use a
    # far-future date for header-style files that carry no expiry information.
    expires = str(int(time.time()) + 10 * 365 * 24 * 3600)
    cookie_domain = domain.lstrip(".")
    netscape_lines = ["# Netscape HTTP Cookie File"]
    for name, value in pairs:
        netscape_lines.append(f".{cookie_domain}\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}")
    logger.debug("normalized cookies to %d lines", len(netscape_lines))
    return "\n".join(netscape_lines)


def _merge_netscape_cookies(existing: str, additional: str) -> str:
    """Merge two Netscape cookie files, letting ``additional`` overwrite duplicates."""
    cookies: dict[tuple[str, str], str] = {}
    for line in (existing + "\n" + additional).splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) == 7:
            cookies[(fields[0], fields[5])] = line
    return "\n".join(["# Netscape HTTP Cookie File", *cookies.values()])


def _is_bot_detection_error(exc: BaseException) -> bool:
    """Return ``True`` when extraction failed due to bot detection (sign in required)."""
    message = str(exc).lower()
    return (
        "sign in to confirm you" in message
        and "not a bot" in message
    ) or "this helps protect our community" in message


class BaseScraper:
    """Run yt-dlp format selection for a URL and return the resolved info dict.

    Parameters
    ----------
    js_runtime:
        JavaScript runtime to use for signature challenges: "node", "deno", or None.
        YouTube requires "deno" (or "node" with n_m3u8dl-re). Other platforms may use "node".
    use_remote_components:
        Load remote yt-dlp components (e.g. ``ejs:github``). Required for
        YouTube to keep progressive formats; disabled by default for other
        platforms to avoid an extra network hop to GitHub.
    cookies_from_browser:
        Browser name to extract cookies from (e.g., "chrome", "firefox", "edge").
    cookies_file:
        Path to a cookies file in Netscape format or a raw cookie header.
    auto_cookies_url:
        URL to visit for automatic cookie extraction when bot detection triggers.
        If set, enables autonomous cookie refresh via Playwright.
    auto_cookies_domain:
        Domain filter for cookie extraction (e.g., "youtube.com").
    """

    def __init__(
        self,
        js_runtime: str | None = "node",
        js_runtime_path: Optional[str] = None,
        use_remote_components: bool = False,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        auto_cookies_url: Optional[str] = None,
        auto_cookies_domain: Optional[str] = None,
        player_clients: Optional[list[str]] = None,
        pot_provider_server_home: Optional[str] = None,
    ) -> None:
        self._js_runtime = js_runtime
        self._js_runtime_path = js_runtime_path
        self._use_remote_components = use_remote_components
        self._cookies_from_browser = cookies_from_browser
        self._cookies_file = cookies_file
        self._auto_cookies_url = auto_cookies_url
        self._auto_cookies_domain = auto_cookies_domain
        self._player_clients = player_clients
        self._pot_provider_server_home = pot_provider_server_home
        self._cookies_refreshed = False
        self._cookiefile_path: str | None = None

        # Resolve the runtime once per scraper instead of mutating PATH and
        # probing the filesystem on every extraction attempt.
        self._runtime_path_resolved = (
            self._runtime_path(js_runtime, js_runtime_path) if js_runtime else None
        )
        if self._runtime_path_resolved:
            binary_dir = str(Path(self._runtime_path_resolved).parent)
            if binary_dir not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = f"{binary_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            logger.debug("resolved %s runtime at %s", js_runtime, self._runtime_path_resolved)
        elif js_runtime:
            logger.warning("JS runtime %s not found on PATH", js_runtime)

    @staticmethod
    def _runtime_path(runtime: str, configured: str | None) -> str | None:
        """Resolve the executable matching the requested JS runtime name."""
        if configured and Path(configured).name == runtime:
            return configured
        found = shutil.which(runtime)
        if found:
            return found
        fallback = f"/usr/local/bin/{runtime}"
        return fallback if Path(fallback).exists() else None

    @property
    def _base_opts(self) -> dict[str, Any]:
        """Build yt-dlp options shared by every extraction call."""
        opts: dict[str, Any] = {
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 15,
        }

        proxy = _configured_proxy()
        if proxy:
            opts["proxy"] = proxy
            logger.info("yt-dlp outbound proxy configured")

        if self._js_runtime:
            opts["js_runtimes"] = {
                self._js_runtime: {"path": self._runtime_path_resolved}
                if self._runtime_path_resolved else {}
            }

        if self._use_remote_components:
            opts["remote_components"] = ["ejs:github"]

        extractor_args: dict[str, dict[str, list[str]]] = {}
        if self._player_clients:
            extractor_args["youtube"] = {"player_client": list(self._player_clients)}
        # The bgutil plugin looks in ~/bgutil-ytdlp-pot-provider by default,
        # which does not exist in the image. Point it at the installed server;
        # yt-dlp expects each extractor-arg value to be a list.
        if self._pot_provider_server_home:
            extractor_args["youtubepot-bgutilscript"] = {
                "server_home": [self._pot_provider_server_home]
            }
        if extractor_args:
            opts["extractor_args"] = extractor_args

        # Cookie strategy: a real file always wins. Browser extraction is only
        # a fallback for local development — a container has no browser profile.
        # The normalized path is cached per request so repeated extraction calls
        # do not rewrite the same file, while a new request re-reads the source.
        cookie_source = self._cookiefile_path
        if cookie_source is None and self._cookies_file:
            content = _read_cookies_file(self._cookies_file)
            if content is not None:
                normalized = _normalize_cookies_content(
                    content, self._auto_cookies_domain or "youtube.com"
                )
                writable_path = Path("/app/cookies") / (
                    f"{Path(self._cookies_file).stem}_normalized.txt"
                )
                try:
                    writable_path.parent.mkdir(parents=True, exist_ok=True)
                    writable_path.write_text(normalized, encoding="utf-8")
                    self._cookiefile_path = str(writable_path)
                    cookie_source = self._cookiefile_path
                except Exception as exc:
                    logger.warning("Failed to write cookies to %s: %s", writable_path, exc)

        if cookie_source:
            opts["cookiefile"] = cookie_source
        elif self._cookies_from_browser:
            opts["cookies_from_browser"] = self._cookies_from_browser

        logger.info(
            "_base_opts: js_runtimes=%s, cookiefile=%s, cookies_from_browser=%s",
            opts.get("js_runtimes"), opts.get("cookiefile"), opts.get("cookies_from_browser"),
        )
        return opts

    @staticmethod
    def _is_rate_limited(exc: BaseException) -> bool:
        """Return ``True`` when extraction failed with a temporary HTTP limit."""
        message = str(exc)
        return "HTTP Error 403" in message or "HTTP Error 429" in message

    async def _refresh_cookies(self, url: str | None = None, force: bool = False) -> bool:
        """Rebuild the normalized cookie file and try a Playwright refresh.

        The mounted cookies may contain auth cookies Playwright cannot obtain,
        so fresh cookies are merged into the existing file instead of replacing it.
        """
        if self._cookies_refreshed and not force:
            return False

        content = _read_cookies_file(self._cookies_file) if self._cookies_file else None
        if content is None:
            logger.warning("_refresh_cookies: cookies file invalid")
            return False

        # yt-dlp rewrites the writable copy with only the cookies the site
        # accepted, which can drop auth cookies. Always rebuild it from the
        # mounted source before retrying so the retry gets the full set again.
        normalized = _normalize_cookies_content(
            content, self._auto_cookies_domain or "youtube.com"
        )
        cookiefile = self._cookiefile_path
        if not cookiefile:
            cookiefile = str(
                Path("/app/cookies")
                / f"{Path(self._cookies_file).stem}_normalized.txt"
            )
            self._cookiefile_path = cookiefile
        try:
            Path(cookiefile).write_text(normalized, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.warning("_refresh_cookies: cannot write %s: %s", cookiefile, exc)
            return False

        if os.getenv("COOKIES_AUTO_REFRESH", "true").lower() in ("1", "true", "yes"):
            try:
                from src.platforms.core.cookies import extract_cookies

                fresh, found = await extract_cookies(
                    url or self._auto_cookies_url or "https://www.youtube.com",
                    domain_filter=self._auto_cookies_domain,
                )
                if found:
                    # Source cookies are authenticated; let them win over same-
                    # named anonymous cookies gathered by Playwright.
                    Path(cookiefile).write_text(
                        _merge_netscape_cookies(fresh, normalized), encoding="utf-8"
                    )
                    logger.info("_refresh_cookies: merged fresh cookies into %s", cookiefile)
            except Exception as exc:  # noqa: BLE001 - refresh is best-effort
                logger.warning("_refresh_cookies: Playwright refresh failed: %s", exc)

        self._cookies_refreshed = True
        return True

    async def _run_extraction(self, url: str, fmt: str | None = None) -> dict[str, Any]:
        """Run yt-dlp once with retries for temporary limits and bot checks."""
        opts = dict(self._base_opts)
        if fmt is not None:
            opts["format"] = fmt

        proxy = _configured_proxy()
        # A rotating proxy gives every request a different exit IP, so a single
        # extraction is a lottery: the page, player API and PO-token script can
        # land on different addresses. Retrying simply draws another IP.
        delays = (0.0, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0) if proxy else (0.0, *_RETRY_DELAYS)

        last_error: Exception | None = None
        for index, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            # yt-dlp writes the cookiejar back to the file on exit; restore the
            # pristine source before each retry so it never degrades.
            if proxy and index and opts.get("cookiefile") and self._cookies_file:
                content = _read_cookies_file(self._cookies_file)
                if content is not None:
                    try:
                        Path(opts["cookiefile"]).write_text(
                            _normalize_cookies_content(
                                content, self._auto_cookies_domain or "youtube.com"
                            ),
                            encoding="utf-8",
                        )
                    except Exception:  # noqa: BLE001 - best effort
                        pass
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return await asyncio.to_thread(ydl.extract_info, url, download=False)
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = exc
                logger.warning("yt-dlp extraction failed for %s: %s", url, exc)

                if _is_bot_detection_error(exc):
                    if proxy:
                        logger.warning(
                            "Bot-check from a proxy exit IP; retrying with another "
                            "one (attempt %d/%d)", index + 1, len(delays)
                        )
                        continue
                    if not self._cookies_refreshed:
                        logger.warning(
                            "YouTube bot-check for %s (IP-level: cookies and player "
                            "clients do not bypass it); set YOUTUBE_PROXY to use "
                            "another IP", url
                        )
                        if await self._refresh_cookies(url, force=True):
                            # The normalized cookiefile is updated in place and
                            # `opts` still points at it — rebuilding would
                            # overwrite the freshly merged cookies.
                            continue
                        logger.error("Cookie refresh failed, cannot bypass bot detection")

                if not self._is_rate_limited(exc):
                    raise
                logger.warning("Rate limited while extracting %s (attempt %d)", url, index + 1)

        raise DownloadError(f"Unable to extract {url}: {last_error}")

    async def _extract(self, url: str, fmt: str) -> dict[str, Any]:
        """Resolve a single format through yt-dlp."""
        return await self._run_extraction(url=url, fmt=fmt)

    async def resolve_audio(self, url: str, format_id: str) -> dict[str, Any]:
        """Resolve a single audio format to its direct media URL."""
        info = await self._extract(url=url, fmt=format_id)
        media_url = info.get("url")
        if not media_url:
            raise DownloadError(f"Format {format_id} is not available for {url}")
        return info

    async def resolve_streams(self, url: str, height: int) -> dict[str, Any]:
        """Resolve the best video stream for ``height`` plus its audio."""
        # `height<=` instead of `height=`: the exact height is not always
        # available, which would fail the whole request.
        fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        return await self._extract(url=url, fmt=fmt)

    async def get_post_info(self, url: str) -> dict:
        """Extract raw post metadata without downloading anything."""
        return dict(await self._run_extraction(url=url))

    async def download_to_file(
        self,
        url: str,
        *,
        format_selector: str,
        out_dir: str,
        filename: str = "%(id)s.%(ext)s",
        merge_output_format: str | None = None,
    ) -> Path:
        """Download ``url`` with the same options used for extraction.

        This matters for YouTube: the resolved media URLs are signed and bound
        to cookies, visitor data and a PO token. Fetching them later with a bare
        urllib/ffmpeg request gets HTTP 403, while letting yt-dlp perform the
        download in the same run works reliably.
        """
        opts: dict[str, Any] = {
            **self._base_opts,
            "skip_download": False,
            "format": format_selector,
            "outtmpl": str(Path(out_dir) / filename),
            "quiet": True,
            "no_warnings": True,
        }
        if merge_output_format:
            opts["merge_output_format"] = merge_output_format

        loop = asyncio.get_running_loop()

        def _download() -> Path:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                try:
                    candidate = Path(ydl.prepare_filename(info))
                    if candidate.exists():
                        return candidate
                except Exception:  # noqa: BLE001 - fall back to the newest file
                    pass
                files = [p for p in Path(out_dir).iterdir() if p.is_file()]
                if not files:
                    raise DownloadError(f"yt-dlp did not produce a file for {url}")
                return max(files, key=lambda p: p.stat().st_mtime)

        return await loop.run_in_executor(None, _download)
