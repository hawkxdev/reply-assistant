"""HTTP application factory."""

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.resources import files

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from reply_assistant import __version__
from reply_assistant.crm_event import CRMEventError, parse_crm_event
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import (
    FallbackClient,
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


def _error(
    status: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build one error answer."""
    body = ErrorBody(code=code, message=message)
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


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


# === Webhook ===

logger = logging.getLogger(__name__)

CRM_FORM_TYPE = 'application/x-www-form-urlencoded'
CRM_BODY_LIMIT = 65536


def _is_crm_form(media_type: str) -> bool:
    """Match the CRM form media type."""
    base = media_type.partition(';')[0].strip().lower()
    return base == CRM_FORM_TYPE


async def _limited_body(request: Request) -> bytes:
    """Read the body within the size bound."""
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > CRM_BODY_LIMIT:
            raise StarletteHTTPException(413)
        chunks.append(chunk)
    return b''.join(chunks)


async def process_crm_message(
    message: str, kb: KnowledgeBase, client: ModelClient
) -> None:
    """Suggest for one acknowledged event."""
    try:
        await suggest(SuggestionRequest(message=message), kb, client)
    except ProviderError:
        logger.warning('CRM suggestion failed: provider_error')
    except SuggestionRejectedError:
        logger.warning('CRM suggestion failed: suggestion_rejected')
    except Exception:
        logger.warning('CRM suggestion failed: internal_error')
    else:
        logger.info('CRM suggestion ready')


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
        """Manage owned application parts."""
        owned: list[OpenAICompatibleClient | FallbackClient] = []
        if parts.kb is None or parts.client is None:
            settings = Settings()
            if parts.kb is None:
                parts.kb = await load_knowledge_base(settings.kb_path)
            if parts.client is None:
                built: OpenAICompatibleClient | FallbackClient
                if settings.fallback_provider_base_url is None:
                    built = OpenAICompatibleClient.from_settings(settings)
                else:
                    built = FallbackClient.from_settings(settings)
                parts.client = built
                owned.append(built)
        try:
            yield
        finally:
            for client in owned:
                await client.aclose()
            if owned:
                parts.client = None

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

    @app.exception_handler(CRMEventError)
    async def invalid_crm_event(request: Request, error: CRMEventError) -> JSONResponse:
        """Answer an invalid CRM event."""
        return _error(422, 'invalid_crm_event', 'the CRM message event is invalid')

    @app.exception_handler(StarletteHTTPException)
    async def framework_failed(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        """Answer a framework error."""
        if error.status_code == 404:
            return _error(404, 'not_found', 'the path does not exist', error.headers)
        if error.status_code == 405:
            return _error(
                405, 'method_not_allowed', 'the method is not allowed', error.headers
            )
        return _error(
            error.status_code,
            'http_error',
            'the request was not accepted',
            error.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_failed(request: Request, error: Exception) -> JSONResponse:
        """Answer an unexpected failure."""
        return _error(500, 'internal_error', 'an unexpected error occurred')

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

    @app.post('/webhooks/crm/messages')
    async def crm_message(
        request: Request, background: BackgroundTasks
    ) -> JSONResponse:
        """Acknowledge one CRM message event."""
        if parts.kb is None or parts.client is None:
            raise RuntimeError('the application did not start')
        if not _is_crm_form(request.headers.get('content-type', '')):
            raise StarletteHTTPException(415)
        body = await _limited_body(request)
        message = parse_crm_event(body)
        background.add_task(process_crm_message, message, parts.kb, parts.client)
        return JSONResponse(
            status_code=202, content={'accepted': True}, background=background
        )

    return app
