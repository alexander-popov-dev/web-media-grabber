from src.platforms.core.parser import BaseParser


class YoutubeParser(BaseParser):
    """YouTube parser.

    YouTube increasingly serves SABR-only/HLS formats (itags 91-93, 96, 301,
    ...) instead of direct HTTPS DASH formats. They carry normal height/fps
    metadata and yt-dlp can download them, so allow ``m3u8*`` protocols on top
    of the shared parsing logic in :class:`BaseParser`.
    """

    def __init__(self, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            allowed_protocols=("https", "m3u8"),
        )
