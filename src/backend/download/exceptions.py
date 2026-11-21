class BaseDownloadError(Exception):
    pass

class PlatformNotSupported(BaseDownloadError):
    pass