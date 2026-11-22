from urllib.parse import urlencode

from src.platforms.core.schemas import Audio, Post, Video


class YoutubeParser:
    """Превращает ответ yt-dlp в схему Post с ссылками на скачивание."""

    # Только расширения, которые бэкенд может корректно отдать браузеру.
    # webp и прочие не-медиа форматы выпадают из списка форматов.
    SUPPORTED_VIDEO_EXTS = {"mp4", "webm"}
    SUPPORTED_AUDIO_EXTS = {"m4a", "webm", "mp3", "aac", "opus"}

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @staticmethod
    def _has(codec: str | None) -> bool:
        return codec not in (None, "none")

    @staticmethod
    def _size(fmt: dict, duration: int | None = None) -> float:
        """Размер в байтах.

        Если yt-dlp не вернул ``filesize``/``filesize_approx`` (часто для
        высоких разрешений), оцениваем через битрейт ``tbr`` и длительность.
        """
        size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        if size and duration:
            return size
        if duration and fmt.get("tbr"):
            # tbr в кбит/с → байты = kbit * 1000 / 8 * seconds
            return fmt["tbr"] * 1000 * duration / 8
        return size

    @staticmethod
    def _fmt_size(size: float) -> str:
        """Человекочитаемый размер: приоритет килобайтам, МБ — для крупных файлов."""
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
        formats = [
            f for f in response.get("formats", [])
            if f.get("url") and f.get("protocol") == "https"
            and f.get("ext") in (None, *self.SUPPORTED_VIDEO_EXTS, *self.SUPPORTED_AUDIO_EXTS)
        ]

        audio_streams = [
            f for f in formats
            if self._has(f.get("acodec")) and not self._has(f.get("vcodec"))
            and f.get("ext") in self.SUPPORTED_AUDIO_EXTS
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
            if f.get("ext") not in self.SUPPORTED_VIDEO_EXTS:
                continue
            if h not in by_height or self._size(f, duration) > self._size(by_height[h], duration):
                by_height[h] = f

        videos = []
        for h, f in sorted(by_height.items(), reverse=True):
            has_audio = self._has(f.get("acodec"))
            total = self._size(f, duration) + (0 if has_audio else audio_size)
            videos.append(Video(
                url=f"{self._base_url}/download?" + urlencode({"url": url, "height": h}),
                # The download endpoint remuxes every quality into a
                # fragmented MP4, so the label must match the served file.
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

        audios = []
        for abr, f in sorted(by_bitrate.items(), reverse=True):
            audios.append(Audio(
                url=f"{self._base_url}/download?" + urlencode({"url": url, "format_id": f["format_id"]}),
                format=(f.get("ext") or "").upper(),
                bitrate=f"{abr} kbps",
                size=self._fmt_size(self._size(f, duration)),
            ))
        return audios
