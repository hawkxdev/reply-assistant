"""HTTP application factory."""

import logging
import secrets
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from importlib.resources import files

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, SecretStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from reply_assistant import __version__
from reply_assistant.crm_event import CRMEventError, parse_crm_event
from reply_assistant.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseError,
    load_knowledge_base,
)
from reply_assistant.model_client import (
    FallbackClient,
    ModelClient,
    OpenAICompatibleClient,
    ProviderError,
)
from reply_assistant.registry import Registry, RegistryError, load_registry
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


class UnauthorizedError(Exception):
    """Missing or wrong token."""


class CatalogueSelectionError(Exception):
    """Invalid demo catalogue selection."""


class CatalogueUnavailableError(Exception):
    """Unavailable demo language catalogue."""


def _tokens_match(given: str, expected: str) -> bool:
    """Compare two tokens."""
    return secrets.compare_digest(given.encode('utf-8'), expected.encode('utf-8'))


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
    """Match the CRM form."""
    base = media_type.partition(';')[0].strip().lower()
    return base == CRM_FORM_TYPE


async def _limited_body(request: Request) -> bytes:
    """Read the bounded body."""
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
    """Suggest for the event."""
    try:
        await suggest(SuggestionRequest(message=message), kb, client)
    except ProviderError:
        logger.warning('CRM suggestion failed: provider_error')
    except SuggestionRejectedError:
        logger.warning('CRM suggestion failed: suggestion_rejected')
    except Exception:
        logger.error('CRM suggestion failed: internal_error')
    else:
        logger.info('CRM suggestion ready')


# === Factory ===


@dataclass
class Dependencies:
    """Parts the endpoints use."""

    kb: KnowledgeBase | None = None
    client: ModelClient | None = None
    registry: Registry | None = None
    api_token: SecretStr | None = None
    demo_catalogues: dict[str, str] = field(default_factory=dict)

    async def select_kb(
        self,
        client_id: str | None,
        catalogue_language: str | None = None,
    ) -> KnowledgeBase:
        """Select the serving base."""
        if catalogue_language is not None:
            if catalogue_language not in {'en', 'ru'} or client_id is not None:
                raise CatalogueSelectionError()
            if self.demo_catalogues:
                if self.registry is None:
                    raise CatalogueUnavailableError()
                try:
                    selected = await self.registry.select(
                        self.demo_catalogues[catalogue_language],
                        required=True,
                    )
                except RegistryError as error:
                    raise CatalogueUnavailableError() from error
            else:
                selected = await self.select_kb(None)
            if selected.language != catalogue_language:
                raise CatalogueUnavailableError()
            return selected
        if self.registry is not None:
            return await self.registry.select(client_id)
        if self.kb is None:
            raise RuntimeError('the application did not start')
        return self.kb


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
            parts.api_token = settings.api_token
            parts.demo_catalogues = settings.demo_catalogues
            if parts.kb is None:
                if settings.kb_registry is not None:
                    loaded = await load_registry(settings.kb_registry)
                    parts.registry = loaded
                    parts.kb = loaded.default_kb
                    for language, alias in parts.demo_catalogues.items():
                        selected = await loaded.select(alias, required=True)
                        if selected.language != language:
                            raise RegistryError(
                                'the demo catalogue language is invalid'
                            )
                else:
                    kb_path = settings.kb_path
                    if kb_path is None:
                        raise RuntimeError('no knowledge base source is configured')
                    parts.kb = await load_knowledge_base(kb_path)
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
        """Answer an invalid event."""
        return _error(422, 'invalid_crm_event', 'the CRM message event is invalid')

    @app.exception_handler(UnauthorizedError)
    async def unauthorized(request: Request, error: UnauthorizedError) -> JSONResponse:
        """Answer an unauthorized request."""
        return _error(401, 'unauthorized', 'the API token is missing or wrong')

    @app.exception_handler(RegistryError)
    async def registry_failed(request: Request, error: RegistryError) -> JSONResponse:
        """Answer a registry failure."""
        return _error(500, 'registry_error', 'the knowledge base registry is invalid')

    @app.exception_handler(CatalogueSelectionError)
    async def invalid_catalogue_selection(
        request: Request,
        error: CatalogueSelectionError,
    ) -> JSONResponse:
        """Reject invalid catalogue selection."""
        return _error(
            400, 'invalid_catalogue_selection', 'the catalogue selection is invalid'
        )

    @app.exception_handler(CatalogueUnavailableError)
    async def unavailable_catalogue(
        request: Request,
        error: CatalogueUnavailableError,
    ) -> JSONResponse:
        """Refuse unavailable language catalogue."""
        return _error(
            503, 'catalogue_unavailable', 'the selected catalogue is unavailable'
        )

    @app.exception_handler(KnowledgeBaseError)
    async def invalid_base(request: Request, error: KnowledgeBaseError) -> JSONResponse:
        """Answer an invalid base."""
        return _error(500, 'kb_error', 'the knowledge base is invalid')

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

    async def require_token(request: Request) -> None:
        """Check the shared token."""
        token = parts.api_token
        if token is not None and not _tokens_match(
            request.headers.get('X-API-Token', ''), token.get_secret_value()
        ):
            raise UnauthorizedError()

    @app.post('/api/suggest', dependencies=[Depends(require_token)])
    async def suggest_answer(
        request: Request, payload: SuggestionRequest
    ) -> Suggestion:
        """Return one checked suggestion."""
        if parts.client is None:
            raise RuntimeError('the application did not start')
        kb = await parts.select_kb(
            request.headers.get('X-Client-Id'),
            request.headers.get('X-Catalogue-Language'),
        )
        return await suggest(payload, kb, parts.client)

    @app.post('/webhooks/crm/messages', dependencies=[Depends(require_token)])
    async def crm_message(
        request: Request, background: BackgroundTasks
    ) -> JSONResponse:
        """Acknowledge one CRM event."""
        if parts.client is None:
            raise RuntimeError('the application did not start')
        if not _is_crm_form(request.headers.get('content-type', '')):
            raise StarletteHTTPException(415)
        body = await _limited_body(request)
        message = parse_crm_event(body)
        kb = await parts.select_kb(request.headers.get('X-Client-Id'))
        background.add_task(process_crm_message, message, kb, parts.client)
        return JSONResponse(
            status_code=202, content={'accepted': True}, background=background
        )

    return app
