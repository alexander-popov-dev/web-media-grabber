from functools import cache

from pydantic import Field

from src.core.settings import BaseProjectSettings


class BackendSettings(BaseProjectSettings):
    """HTTP-layer configuration for the FastAPI backend."""

    cors_origins: list[str] = Field(alias="CORS_ORIGINS", default=[])
    # Public hostname used in download links and the Traefik Host() rule.
    # Defaults keep local runs working without any .env file.
    backend_host: str = Field(alias="BACKEND_HOST", default="127.0.0.1")
    backend_port: int = Field(alias="BACKEND_PORT", default=8000)

    @property
    def get_base_url(self) -> str:
        """Origin embedded in the download links returned to the browser."""
        if self.debug:
            return f"http://{self.backend_host}:{self.backend_port}"
        # In production 443 is terminated by Traefik, so no port is needed.
        return f"https://{self.backend_host}"


# noinspection PyArgumentList
@cache
def get_backend_settings() -> BackendSettings:
    """Return the singleton BackendSettings instance."""
    return BackendSettings()  # pyright: ignore[reportCallIssue]
