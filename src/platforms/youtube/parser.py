from urllib.parse import urlencode

from src.platforms.core.parser import BaseParser
from src.platforms.core.schemas import Audio, Post, Video


class YoutubeParser(BaseParser):
    """Превращает ответ yt-dlp в схему Post с ссылками на скачивание.

    YouTube specifics:
    - video extensions limited to mp4/webm (what ffmpeg can remux into MP4)
    - audio extensions limited to m4a/webm/mp3/aac/opus
    - size estimated via tbr when filesize is missing
    """

    def __init__(self, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            supported_video_exts={"mp4", "webm"},
            supported_audio_exts={"m4a", "webm", "mp3", "aac", "opus"},
        )

    def parse(self, response: dict) -> Post:
        url = response["webpage_url"]
        duration = response.get("duration")
        formats = [
            f for f in response.get("formats", [])
            if f.get("url") and f.get("protocol") == "https"
            and f.get("ext") in (
                None,
                *self._supported_video_exts,
                *self._supported_audio_exts,
            )
        ]

        audio_streams = [
            f for f in formats
            if self._has(f.get("acodec")) and not self._has(f.get("vcodec"))
            and f.get("ext") in self._supported_audio_exts
        ]
        audio_streams.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
        best_audio_size = self._size(audio_streams[0], duration) if audio_streams else 0

        return Post(
            url=url,
            title=response["title"],
            author=response.get("uploader") or response.get("channel") or "",
            thumbnail=response.get("thumbnail", "-"),
            duration=response.get("duration_string", "-"),
            videos=self._build_videos(formats, url, best_audio_size, duration),
            audios=self._build_audios(audio_streams, url, duration),
        )
