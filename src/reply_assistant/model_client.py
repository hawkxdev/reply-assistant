"""Client of a model provider."""

import json
from dataclasses import dataclass
from typing import Any, Protocol, Self

import httpx2
from pydantic import SecretStr

from reply_assistant.settings import Settings

# === Result ===


@dataclass(frozen=True)
class Usage:
    """Tokens spent on one reply."""

    input_tokens: int
    output_tokens: int
    provider: str


@dataclass(frozen=True)
class Completion:
    """Text and usage together."""

    text: str
    usage: Usage


# === Failure ===


class ProviderError(Exception):
    """Failure of a provider."""

    def __init__(self, provider: str, kind: str, message: str) -> None:
        """Keep the failure details."""
        super().__init__(message)
        self.provider = provider
        self.kind = kind


# === Interface ===


class ModelClient(Protocol):
    """One way to call a model."""

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return one completion."""
        ...


# === Client ===

_TIMEOUT = httpx2.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_JSON_MODE_RULE = 'Answer with one JSON object that follows this JSON schema: '


class OpenAICompatibleClient:
    """Client of an OpenAI compatible endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: SecretStr,
        model: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        json_mode: bool = False,
    ) -> None:
        """Store the provider details."""
        self._provider = httpx2.URL(base_url).host
        self._url = f'{base_url.rstrip("/")}/chat/completions'
        self._api_key = api_key
        self._model = model
        self._json_mode = json_mode
        self._client = httpx2.AsyncClient(transport=transport, timeout=_TIMEOUT)

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
    ) -> Self:
        """Build the client from settings."""
        return cls(
            base_url=settings.provider_base_url,
            api_key=settings.provider_api_key,
            model=settings.provider_model,
            transport=transport,
        )

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return one completion."""
        try:
            response = await self._client.post(
                self._url,
                headers={'Authorization': f'Bearer {self._api_key.get_secret_value()}'},
                json={
                    'model': self._model,
                    'messages': self._messages(messages, schema),
                    'response_format': self._response_format(schema),
                },
            )
        except httpx2.TimeoutException as error:
            raise self._error('timeout', 'timed out') from error
        except httpx2.TransportError as error:
            raise self._error('connection', 'cannot be reached') from error
        return self._completion(response)

    def _messages(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Build the request messages."""
        if not self._json_mode:
            return messages
        rule = f'{_JSON_MODE_RULE}{json.dumps(schema)}'
        return [*messages, {'role': 'system', 'content': rule}]

    def _response_format(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Build the response format."""
        if self._json_mode:
            return {'type': 'json_object'}
        return {
            'type': 'json_schema',
            'json_schema': {
                'name': 'suggestion',
                'strict': True,
                'schema': schema,
            },
        }

    def _completion(self, response: httpx2.Response) -> Completion:
        """Parse the provider reply."""
        if response.status_code != 200:
            raise self._error(
                self._kind(response.status_code),
                f'answered with status {response.status_code}',
            )
        try:
            data = response.json()
            text = data['choices'][0]['message']['content']
            counts = (
                data['usage']['prompt_tokens'],
                data['usage']['completion_tokens'],
            )
        except (ValueError, TypeError, KeyError, IndexError) as error:
            raise self._error('response', 'sent an unreadable reply') from error
        if not isinstance(text, str):
            raise self._error('response', 'sent a reply without text')
        for count in counts:
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise self._error('response', 'sent an invalid token count')
        return Completion(
            text=text,
            usage=Usage(
                input_tokens=counts[0],
                output_tokens=counts[1],
                provider=self._provider,
            ),
        )

    def _kind(self, status: int) -> str:
        """Kind of a status failure."""
        if status == 429:
            return 'rate_limit'
        if status >= 500:
            return 'server'
        return 'request'

    def _error(self, kind: str, message: str) -> ProviderError:
        """Build a provider error."""
        return ProviderError(self._provider, kind, f'{self._provider} {message}')
