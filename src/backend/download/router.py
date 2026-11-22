from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, HTTPException
from starlette import status

from src.backend.download.schemas import DownloadRequest, DownloadResponse
from src.backend.download.service import DownloadService

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
