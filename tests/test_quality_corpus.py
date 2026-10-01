"""Quality document loading tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from reply_assistant.quality_corpus import QualityInputError, load_quality_document

DATA = Path(__file__).parents[1] / 'evals' / 'quality' / 'v1'


def write_document(folder: Path, payload: dict[str, Any]) -> Path:
    """Write one modified payload."""
    path = folder / 'input.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


async def test_unknown_document_kind_is_rejected(tmp_path: Path) -> None:
    payload = json.loads((DATA / 'sources.json').read_text())
    payload['document_kind'] = 'quality_nothing'

    with pytest.raises(QualityInputError) as caught:
        await load_quality_document(write_document(tmp_path, payload))

    assert caught.value.code == 'schema'


async def test_malformed_hash_pin_is_rejected(tmp_path: Path) -> None:
    payload = json.loads((DATA / 'examples' / 'corpus-valid.json').read_text())
    payload['questions_sha256'] = 'not-a-sha256-pin'

    with pytest.raises(QualityInputError) as caught:
        await load_quality_document(write_document(tmp_path, payload))

    assert caught.value.code == 'schema'


async def test_empty_case_id_is_rejected(tmp_path: Path) -> None:
    payload = json.loads((DATA / 'examples' / 'corpus-valid.json').read_text())
    payload['cases'][0]['id'] = ''

    with pytest.raises(QualityInputError) as caught:
        await load_quality_document(write_document(tmp_path, payload))

    assert caught.value.code == 'schema'
