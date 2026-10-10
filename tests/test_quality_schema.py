"""Quality schema validator tests."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from reply_assistant.quality_schema import validate_quality_document

DATA = Path(__file__).parents[1] / 'evals' / 'quality' / 'v1'


def sources_payload() -> dict[str, Any]:
    """Read the sources document."""
    payload: dict[str, Any] = json.loads((DATA / 'sources.json').read_text())
    return payload


@pytest.mark.parametrize(
    'value',
    [2],
    ids=['unsupported-integer'],
)
def test_wrong_version_value_is_rejected(value: Any) -> None:
    payload = sources_payload()
    payload['schema_version'] = value

    with pytest.raises(ValidationError):
        validate_quality_document(payload)
