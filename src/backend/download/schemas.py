from pydantic import BaseModel

from src.platforms.core.schemas import Post


class DownloadRequest(BaseModel):
    url: str

class DownloadResponse(BaseModel):
    post: Post