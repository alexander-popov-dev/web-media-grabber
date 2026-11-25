from pydantic import BaseModel

from src.platforms.core.schemas import Post


class DownloadResponse(BaseModel):
    post: Post
