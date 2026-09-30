"""Suggestion service function."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer

from reply_assistant.checks import (
    CheckError,
    append_disclaimer,
    check_no_forbidden_claim,
    check_product_exists,
)
from reply_assistant.knowledge_base import KnowledgeBase
from reply_assistant.model_client import ModelClient
from reply_assistant.prompt import build_messages
from reply_assistant.suggestion import (
    ModelOutput,
    ModelOutputError,
    SuggestionRequest,
    output_schema,
    parse_model_output,
)

# === Reports ===


class CheckReport(BaseModel):
    """Outcome of the checks."""

    rejected: list[str]
    disclaimer_appended: bool


class FallbackSwitch(BaseModel):
    """One provider switch."""

    primary: str
    secondary: str


class UsageReport(BaseModel):
    """Tokens of one suggestion."""

    input_tokens: int
    output_tokens: int
    provider: str
    attempts: int
    fallbacks: list[FallbackSwitch] = Field(default_factory=list)

    @model_serializer
    def reported(self) -> dict[str, Any]:
        """Omit empty switch lists."""
        data: dict[str, Any] = {
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'provider': self.provider,
            'attempts': self.attempts,
        }
        if self.fallbacks:
            data['fallbacks'] = [
                {'primary': switch.primary, 'secondary': switch.secondary}
                for switch in self.fallbacks
            ]
        return data


class Suggestion(BaseModel):
    """One checked answer."""

    customer_reply: str
    upsell_product_id: str | None
    upsell_hint: str
    kb_match: Literal['found', 'partial', 'none']
    checks: CheckReport
    usage: UsageReport


# === Failure ===


class SuggestionRejectedError(Exception):
    """Second rejection of the answer."""

    def __init__(self, message: str, check: str) -> None:
        """Keep the message and the check."""
        super().__init__(message)
        self.check = check


# === Suggestion ===

RETRY_RULE = (
    'The previous answer was rejected by the check {check}. '
    'Answer again and follow every rule.'
)
ATTEMPT_LIMIT = 2


def _checked(text: str, kb: KnowledgeBase) -> ModelOutput:
    """Check one model answer."""
    output = parse_model_output(text)
    check_product_exists(output, kb)
    check_no_forbidden_claim(output, kb)
    return output


async def suggest(
    request: SuggestionRequest, kb: KnowledgeBase, client: ModelClient
) -> Suggestion:
    """Build one checked suggestion."""
    base = build_messages(kb, request.message)
    schema = output_schema(kb)
    messages = base
    rejected: list[str] = []
    fallbacks: list[FallbackSwitch] = []
    input_tokens = 0
    output_tokens = 0
    provider = ''
    attempts = 0
    while True:
        attempts += 1
        completion = await client.complete(messages, schema)
        input_tokens += completion.usage.input_tokens
        output_tokens += completion.usage.output_tokens
        provider = completion.usage.provider
        if completion.usage.fallback_from is not None:
            fallbacks.append(
                FallbackSwitch(
                    primary=completion.usage.fallback_from,
                    secondary=completion.usage.provider,
                )
            )
        try:
            output = _checked(completion.text, kb)
        except (ModelOutputError, CheckError) as error:
            if attempts == ATTEMPT_LIMIT:
                raise SuggestionRejectedError(
                    f'the answer was rejected by the check {error.check}', error.check
                ) from error
            rejected.append(error.check)
            messages = [
                *base,
                {'role': 'system', 'content': RETRY_RULE.format(check=error.check)},
            ]
        else:
            return Suggestion(
                customer_reply=append_disclaimer(output.customer_reply, kb),
                upsell_product_id=output.upsell_product_id,
                upsell_hint=output.upsell_hint,
                kb_match=output.kb_match,
                checks=CheckReport(
                    rejected=rejected,
                    disclaimer_appended=kb.disclaimer is not None,
                ),
                usage=UsageReport(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider=provider,
                    attempts=attempts,
                    fallbacks=fallbacks,
                ),
            )
