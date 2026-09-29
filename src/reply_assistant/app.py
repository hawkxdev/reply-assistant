"""HTTP application factory."""

from fastapi import FastAPI
from pydantic import BaseModel

from reply_assistant import __version__


class Health(BaseModel):
    """Service health report."""

    status: str
    version: str


def create_app() -> FastAPI:
    """Build the application."""
    app = FastAPI(title='Reply Assistant', version=__version__)

    @app.get('/health')
    async def health() -> Health:
        """Report service health."""
        return Health(status='ok', version=__version__)

    return app
