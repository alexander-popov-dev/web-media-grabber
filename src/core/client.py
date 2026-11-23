import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import field
from typing import AsyncIterator

from curl_cffi import AsyncSession, CurlError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class PlatformConfig(BaseModel):
    headers: dict[str, str] = field(default_factory=dict)
    impersonate: str | None = "chrome"
    proxy: str | None = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_base_delay: float = 1.0


@asynccontextmanager
async def open_session(
        config: PlatformConfig,
) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(
            proxy=config.proxy,
            headers=config.headers,
            impersonate=config.impersonate,
            timeout=config.timeout,
    ) as session:
        yield session


async def request(
        config: PlatformConfig,
        method: str,
        url: str,
        **kwargs,
) -> str:
    last_error: Exception | None = None

    for attempt in range(1, config.max_retries + 1):
        try:
            async with open_session(config) as session:
                response = await session.request(method=method, url=url, **kwargs)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise CurlError(f"Retryable HTTP status {response.status_code} for {url}")

                response.raise_for_status()
                return response.text

        except CurlError as exc:
            last_error = exc
            if attempt == config.max_retries:
                break

            delay = config.retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Request failed (%s %s), attempt %d/%d. Retrying in %.1fs: %s",
                method,
                url,
                attempt,
                config.max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error
