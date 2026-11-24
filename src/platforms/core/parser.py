"""Base parser for all platforms.

Turns a raw yt-dlp info dict into a :class:`Post` with download links. The
logic is platform-agnostic; subclasses only configure which extensions are
considered valid for video and audio.
"""

from urllib.parse import urlencode

from src.platforms.core.schemas import Audio, Post, Video


class BaseParser:
    """Parse a yt-dlp response dict into a :class:`Post`.

    Parameters
    ----------
    base_url:
        Backend origin used to build download links, e.g.
        ``http://127.0.0.1:8000/api/post``.
    supported_video_exts:
        Extensions considered valid for video streams.
    supported_audio_exts:
        Extensions considered valid for audio streams.
    """

    def __init__(
        self,
        base_url: str,
        supported_video_exts: set[str] | None = None,
        supported_audio_exts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url
        self._supported_video_exts = supported_video_exts or {"mp4", "webm"}
        self._supported_audio_exts = supported_audio_exts or {"m4a", "webm", "mp3", "aac", "opus"}

    @staticmethod
    def _has(codec: str | None) -> bool:
        return codec not in (None, "none")

    @staticmethod
    def _size(fmt: dict, duration: int | None = None) -> float:
        """Size in bytes.

        Falls back to an estimate from ``tbr`` (total bitrate) and duration
        when yt-dlp does not provide ``filesize``/``filesize_approx``.
        """
        size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        if size:
            return size
        if duration and fmt.get("tbr"):
            # tbr in kbit/s -> bytes = kbit * 1000 / 8 * seconds
            return fmt["tbr"] * 1000 * duration / 8
        # If we have tbr but no duration, do not guess — return 0 so the UI
        # shows "—" instead of a potentially wrong estimate.
        return 0

    @staticmethod
    def _fmt_size(size: float) -> str:
        """Human-readable size, preferring KB for small files."""
        if not size:
            return "—"
        kb = size / 1024
        if kb < 1024:
            return f"{kb:.0f} KB"
        mb = kb / 1024
        return f"{mb:.1f} MB" if mb < 1024 else f"{mb / 1024:.1f} GB"

    def parse(self, response: dict) -> Post:
        url = response["webpage_url"]
        duration = response.get("duration")
        all_exts = (
            {None}
            | self._supported_video_exts
            | self._supported_audio_exts
        )
        formats = [
            f for f in response.get("formats", [])
            if f.get("url")
            and f.get("protocol") == "https"
            and f.get("ext") in all_exts
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

    def _build_videos(
        self,
        formats: list[dict],
        url: str,
        audio_size: float,
        duration: int | None = None,
    ) -> list[Video]:
        by_height: dict[int, dict] = {}
        for f in formats:
            h = f.get("height")
            if not h or not self._has(f.get("vcodec")):
                continue
            if f.get("ext") not in self._supported_video_exts:
                continue
            if h not in by_height or self._size(f, duration) > self._size(by_height[h], duration):
                by_height[h] = f

        videos: list[Video] = []
        for h, f in sorted(by_height.items(), reverse=True):
            has_audio = self._has(f.get("acodec"))
            total = self._size(f, duration) + (0 if has_audio else audio_size)
            videos.append(Video(
                url=f"{self._base_url}/download?" + urlencode({"url": url, "height": h}),
                # The download endpoint remuxes every quality into a
                # fragmented MP4, so the label matches the served file.
                format="MP4",
                resolution=f"{h}p",
                size=self._fmt_size(total),
            ))
        return videos

    def _build_audios(
        self,
        audio_streams: list[dict],
        url: str,
        duration: int | None = None,
    ) -> list[Audio]:
        by_bitrate: dict[int, dict] = {}
        for f in audio_streams:
            abr = round(f.get("abr") or f.get("tbr") or 0)
            if abr and abr not in by_bitrate:
                by_bitrate[abr] = f

        audios: list[Audio] = []
        for abr, f in sorted(by_bitrate.items(), reverse=True):
            audios.append(Audio(
                url=f"{self._base_url}/download?" + urlencode({"url": url, "format_id": f["format_id"]}),
                format=(f.get("ext") or "").upper(),
                bitrate=f"{abr} kbps",
                size=self._fmt_size(self._size(f, duration)),
            ))
        return audios
