import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.staticfiles import StaticFiles

from src.backend.download.exceptions import BaseDownloadError, PlatformNotSupported
from src.backend.download.router import router as download_router
from src.backend.settings import get_backend_settings

from dishka.integrations.fastapi import setup_dishka

from src.core.container import get_container

backend_settings = get_backend_settings()

# Static frontend is resolved relative to this file so the server also works
# when it is started from a different working directory.
FRONTEND_DIR = Path(__file__).resolve().parent / "src" / "frontend"


async def download_error_handler(request: Request, exc: BaseDownloadError) -> JSONResponse:
    """Report download-layer errors as JSON instead of an internal traceback."""
    if isinstance(exc, PlatformNotSupported):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


async def backend():
    app = FastAPI(title="MediaDownloader", version="0.0.1")
    setup_dishka(container=get_container(), app=app)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    app.include_router(router=download_router, prefix="/api")
    app.add_exception_handler(BaseDownloadError, download_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=backend_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    config = uvicorn.Config(
        app=app,
        host=backend_settings.backend_host,
        port=backend_settings.backend_port
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == '__main__':
    asyncio.run(backend())
