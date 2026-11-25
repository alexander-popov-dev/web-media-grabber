import time
from pathlib import Path
from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, HTTPException
from starlette import status

from src.backend.download.schemas import DownloadResponse
from src.backend.download.service import DownloadService
from src.platforms.core.cookies import ensure_fresh_cookies

router = APIRouter(prefix="/post", tags=["download"])

_COOKIE_PLATFORMS = ("youtube", "facebook", "instagram", "tiktok", "generic")
_COOKIES_DIR = Path("/app/cookies")


def _cookies_path(platform: str) -> Path:
    """Build a cookies path, rejecting anything outside the cookies directory."""
    if platform not in _COOKIE_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform for cookies: {platform}",
        )
    return _COOKIES_DIR / f"cookies_{platform}.txt"


@router.get(
    path="/get",
    response_model=DownloadResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_post(
        url: str,
        service: Annotated[DownloadService, FromDishka()],
) -> DownloadResponse:
    """Return parsed metadata of a post: title, thumbnail and media formats."""
    return await service.get_download_url(url=url)


# `response_model=None` is required: FastAPI cannot build a response model from
# a `StreamingResponse` return annotation.
@router.get(
    path="/download",
    response_model=None,
    status_code=status.HTTP_200_OK,
)
@inject
async def download_post(
        service: Annotated[DownloadService, FromDishka()],
        url: str,
        format_id: str | None = None,
        height: int | None = None,
        title: str | None = None,
):
    """Stream a media file through the backend."""
    if (format_id is None) == (height is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of format_id or height",
        )
    if format_id:
        return await service.stream_audio(url=url, format_id=format_id, title=title)
    return await service.stream_video(url=url, height=height, title=title)


@router.post(
    path="/cookies/refresh",
    status_code=status.HTTP_200_OK,
)
async def refresh_cookies(
    platform: str,
    url: str,
    domain: str,
    force: bool = False,
) -> dict:
    """Manually refresh cookies for a platform using Playwright."""
    cookies_file = _cookies_path(platform)
    cookies_path = await ensure_fresh_cookies(
        filepath=str(cookies_file),
        url=url,
        domain_filter=domain,
        force_refresh=force,
    )
    if cookies_path:
        return {
            "status": "ok",
            "platform": platform,
            "cookies_file": str(cookies_file),
            "message": "Cookies extracted successfully",
        }
    return {
        "status": "no_cookies",
        "platform": platform,
        "message": "No cookies found for this domain",
    }


@router.get(
    path="/cookies/status",
    status_code=status.HTTP_200_OK,
)
async def cookies_status() -> dict:
    """Check cookies status for all platforms."""
    now = time.time()
    info = {}
    for platform in _COOKIE_PLATFORMS:
        path = _cookies_path(platform)
        exists = path.is_file()
        age_hours = (now - path.stat().st_mtime) / 3600 if exists else None
        info[platform] = {
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else 0,
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
        }
    return {"cookies": info}
