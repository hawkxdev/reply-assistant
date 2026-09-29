"""HTTP application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.resources import files

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from reply_assistant import __version__
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import (
    ModelClient,
    OpenAICompatibleClient,
    ProviderError,
)
from reply_assistant.service import Suggestion, SuggestionRejectedError, suggest
from reply_assistant.settings import Settings
from reply_assistant.suggestion import SuggestionRequest

# === Health ===


class Health(BaseModel):
    """Service health report."""

    name: str
    status: str
    version: str


# === Errors ===


class ErrorBody(BaseModel):
    """Body of an error answer."""

    code: str
    message: str


def _error(status: int, code: str, message: str) -> JSONResponse:
    """Build one error answer."""
    body = ErrorBody(code=code, message=message)
    return JSONResponse(status_code=status, content=body.model_dump())


# === Page ===

PAGE = (
    files('reply_assistant')
    .joinpath('static', 'index.html')
    .read_text(encoding='utf-8')
)
PAGE_ROOT = '<html lang="en">'


def render_page(language: str) -> HTMLResponse:
    """Render the page in one language."""
    return HTMLResponse(PAGE.replace(PAGE_ROOT, f'<html lang="{language}">'))


# === Factory ===


@dataclass
class Dependencies:
    """Parts the endpoints use."""

    kb: KnowledgeBase | None = None
    client: ModelClient | None = None


def create_app(
    kb: KnowledgeBase | None = None, client: ModelClient | None = None
) -> FastAPI:
    """Build the application."""
    parts = Dependencies(kb=kb, client=client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Load the parts the app owns."""
        owned: list[OpenAICompatibleClient] = []
        if parts.kb is None or parts.client is None:
            settings = Settings()
            if parts.kb is None:
                parts.kb = await load_knowledge_base(settings.kb_path)
            if parts.client is None:
                built = OpenAICompatibleClient.from_settings(settings)
                parts.client = built
                owned.append(built)
        try:
            yield
        finally:
            for client in owned:
                await client.aclose()

    app = FastAPI(title='Reply Assistant', version=__version__, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        """Answer an invalid request."""
        return _error(422, 'invalid_request', 'the request body is invalid')

    @app.exception_handler(SuggestionRejectedError)
    async def rejected(
        request: Request, error: SuggestionRejectedError
    ) -> JSONResponse:
        """Answer a rejected answer."""
        message = f'the answer was rejected by the check {error.check}'
        return _error(502, 'suggestion_rejected', message)

    @app.exception_handler(ProviderError)
    async def provider_failed(request: Request, error: ProviderError) -> JSONResponse:
        """Answer a provider failure."""
        if error.kind == 'timeout':
            return _error(504, 'provider_timeout', 'the model provider timed out')
        return _error(502, 'provider_error', 'the model provider failed')

    @app.get('/')
    async def page() -> HTMLResponse:
        """Return the web page."""
        if parts.kb is None:
            raise RuntimeError('the application did not start')
        return render_page(parts.kb.language)

    @app.get('/health')
    async def health() -> Health:
        """Report service health."""
        return Health(name='reply-assistant', status='ok', version=__version__)

    @app.post('/api/suggest')
    async def suggest_answer(request: SuggestionRequest) -> Suggestion:
        """Return one checked suggestion."""
        if parts.kb is None or parts.client is None:
            raise RuntimeError('the application did not start')
        return await suggest(request, parts.kb, parts.client)

    return app
