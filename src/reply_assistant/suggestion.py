"""Suggestion request and model output."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from reply_assistant.knowledge_base import KnowledgeBase

# === Request ===


class SuggestionRequest(BaseModel):
    """Incoming customer message."""

    message: str = Field(min_length=1, max_length=2000)

    @field_validator('message')
    @classmethod
    def reject_blank(cls, value: str) -> str:
        """Reject a blank message."""
        if not value.strip():
            raise ValueError('the message is whitespace only')
        return value


# === Output ===


class ModelOutput(BaseModel):
    """Fields of one suggestion."""

    model_config = ConfigDict(extra='forbid', strict=True)

    customer_reply: str
    upsell_product_id: str | None
    upsell_hint: str
    kb_match: Literal['found', 'partial', 'none']


class ModelOutputError(Exception):
    """Model answer of wrong shape."""

    def __init__(self, message: str, check: str) -> None:
        """Keep the message and the check."""
        super().__init__(message)
        self.check = check


# === Schema ===

MATCH_VALUES = ('found', 'partial', 'none')


def output_schema(kb: KnowledgeBase) -> dict[str, Any]:
    """Schema of the model answer."""
    ids = [product.id for product in kb.products]
    return {
        'type': 'object',
        'properties': {
            'customer_reply': {'type': 'string'},
            'upsell_product_id': {
                'anyOf': [{'type': 'string', 'enum': ids}, {'type': 'null'}]
            },
            'upsell_hint': {'type': 'string'},
            'kb_match': {'type': 'string', 'enum': list(MATCH_VALUES)},
        },
        'required': ['customer_reply', 'upsell_product_id', 'upsell_hint', 'kb_match'],
        'additionalProperties': False,
    }


# === Parsing ===


def parse_model_output(raw: str) -> ModelOutput:
    """Parse the model answer."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ModelOutputError('the answer is not JSON', 'shape') from error
    if not isinstance(data, dict):
        raise ModelOutputError('the answer is not a JSON object', 'shape')
    try:
        return ModelOutput.model_validate(data)
    except ValidationError as error:
        raise ModelOutputError(
            f'the answer has a wrong field: {error}', 'shape'
        ) from error
