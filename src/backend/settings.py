from functools import cache

from pydantic import Field

from src.core.settings import BaseProjectSettings


class BackendSettings(BaseProjectSettings):
    """HTTP-layer configuration for the FastAPI backend."""

    secret_key: str = Field(alias="SECRET_KEY")
    cors_origins: list[str] = Field(alias="CORS_ORIGINS", default=[])
    backend_host: str = Field(alias="BACKEND_HOST")
    backend_port: int = Field(alias="BACKEND_PORT")

    @property
    def get_base_url(self) -> str:
        if self.debug:
            return f"http://{self.backend_host}:{self.backend_port}"
        return f"https://{self.backend_host}"


# noinspection PyArgumentList
@cache
def get_backend_settings() -> BackendSettings:
    """Return the singleton BackendSettings instance."""
    return BackendSettings()  # pyright: ignore[reportCallIssue]