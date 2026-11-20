from pydantic import BaseModel

class Video(BaseModel):
    url: str
    format: str
    resolution: str
    size: str

class Audio(BaseModel):
    url: str
    format: str
    bitrate: str
    size: str

class Post(BaseModel):
    url: str
    title: str
    author: str
    videos: list[Video]
    audios: list[Audio]
