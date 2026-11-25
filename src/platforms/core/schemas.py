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
    thumbnail: str
    duration: str
    videos: list[Video]
    audios: list[Audio]


class ResolvedAudio(BaseModel):
    """Direct link to a single audio format resolved by a platform scraper."""

    url: str
    ext: str
    format: str


class ResolvedStreams(BaseModel):
    """Links required to assemble one downloadable video file.

    ``audio_url`` is ``None`` when the platform already provides a single
    progressive stream that contains both video and audio.
    """

    video_url: str
    audio_url: str | None = None
    height: int
