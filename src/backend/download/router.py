from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, HTTPException
from starlette import status

from src.backend.download.schemas import DownloadRequest, DownloadResponse
from src.backend.download.service import DownloadService
from src.platforms.core.cookies import ensure_fresh_cookies

router = APIRouter(prefix="/post", tags=["download"])


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
    request = DownloadRequest(url=url)
    return await service.get_download_url(request=request)


# `response_model=None` is required: FastAPI builds a response model from the
# return annotation, and a `StreamingResponse | RedirectResponse` union is not
# a valid pydantic type, which would break the route creation.
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
    """Stream a media file through the backend.

    ``format_id`` downloads a single audio format, ``height`` downloads a video
    of the given quality (merged with its audio track by ffmpeg).
    """
    if format_id:
        return await service.stream_audio(url=url, format_id=format_id, title=title)
    if height:
        return await service.stream_video(url=url, height=height, title=title)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Either format_id or height must be provided",
    )


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
    """Manually refresh cookies for a platform using Playwright.

    Args:
        platform: Platform name (youtube, facebook, instagram, tiktok)
        url: URL to visit for cookie extraction
        domain: Domain filter for cookies (e.g., 'youtube.com')
        force: Force refresh even if cookies are fresh

    Returns:
        Status and cookies file path
    """
    cookies_file = f"/app/cookies_{platform}.txt"
    cookies = await ensure_fresh_cookies(
        filepath=f"/app/cookies_{platform}.txt",
        url=url,
        domain_filter=domain,
        force_refresh=True,
    )
    return {
        "status": "ok",
        "platform": platform,
        "cookies_file": cookies_file,
        "cookies_length": len(cookies),
    }


@router.get(
    path="/cookies/status",
    status_code=status.HTTP_200_OK,
)
async def cookies_status() -> dict:
    """Check cookies status for all platforms."""
    import os
    platforms = ["youtube", "facebook", "instagram", "tiktok", "generic"]
    status_info = {}
    for platform in platforms:
        filepath = f"/app/cookies_{platform}.txt"
        exists = os.path.exists(filepath)
        size = os.path.getsize(filepath) if exists else 0
        import time
        age_hours = (time.time() - os.path.getmtime(filepath)) / 3600 if exists else None
        status_info[platform] = {
            "exists": exists,
            "size_bytes": size,
            "age_hours": round(age_hours, 1) if age_hours else None,
        }
    return {"cookies": status_info}
