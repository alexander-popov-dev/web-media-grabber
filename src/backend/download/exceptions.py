class BaseDownloadError(Exception):
    """Base class for errors that are reported to the API client as JSON."""


class PlatformNotSupported(BaseDownloadError):
    """Raised when the requested URL belongs to an unsupported platform."""


class MediaNotAvailable(BaseDownloadError):
    """Raised when the upstream host cannot provide the requested media."""
