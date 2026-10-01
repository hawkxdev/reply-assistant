"""Acceptance for issue 57."""

import importlib
import json
import logging
import threading
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

pytestmark = pytest.mark.xfail(strict=True, reason='issue 57 is not implemented')

# === Data ===

ROOT = Path(__file__).parents[2]
DATA = ROOT / 'evals' / 'quality' / 'v1'
HIDDEN = 'input-value-must-stay-local'
RAW = (
    ' {"document_kind":"quality_sources","schema_version":1,'
    '"rules_id":"factual-assessment-v1","rules_sha256":"'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '","sources":[{"id":"public-en","path":"kb/example-en.yaml","sha256":"'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '","language":"en"}]}\n'
)

# === Fixtures and helpers ===


@pytest.fixture
def loader() -> ModuleType:
    """Import the document loader."""
    return importlib.import_module('reply_assistant.quality_corpus')


def write_document(folder: Path, text: str | bytes) -> Path:
    """Write one test document."""
    path = folder / 'input.json'
    path.write_bytes(text.encode('utf-8') if isinstance(text, str) else text)
    return path


def source_payload() -> dict[str, Any]:
    """Decode the source fixture."""
    return cast(dict[str, Any], json.loads(RAW))


def corpus_payload() -> dict[str, Any]:
    """Read the public example."""
    return cast(
        dict[str, Any],
        json.loads((DATA / 'examples' / 'corpus-valid.json').read_text()),
    )


def generation_payload() -> dict[str, Any]:
    """Build structural generation metadata."""
    payload = corpus_payload()
    origin = payload['cases'][0]['answer_origin']
    origin.update(
        kind='recorded',
        reference='format-only-record.json',
        sha256='0' * 64,
        record_pointer='',
        generation={
            'provider': None,
            'model': None,
            'max_output_tokens': 1,
            'temperature': None,
            'input_tokens': 0,
            'output_tokens': 0,
            'attempts': 1,
            'run_reference': None,
        },
    )
    return payload


# === Valid documents ===


@pytest.mark.parametrize(
    ('name', 'kind'),
    [
        ('sources.json', 'quality_sources'),
        ('facts.json', 'quality_facts'),
        ('examples/questions.json', 'quality_questions'),
        ('examples/corpus-valid.json', 'quality_corpus'),
    ],
)
async def test_loading_preserves_document_content(
    loader: ModuleType, name: str, kind: str
) -> None:
    path = DATA / name
    result = await loader.load_quality_document(path)

    assert result.document.document_kind == kind
    assert result.document.model_dump(mode='json') == json.loads(path.read_text())


@pytest.mark.parametrize(
    ('text', 'digest'),
    [
        (RAW, 'dafb17183ab4184efdd693ffbe52e0d54e206d950ddac89373a023e665fafaa2'),
        (
            RAW.strip(),
            '16288b9663126fd13c81774976a8e03e2f294ece082597ce3ac052cc681c4446',
        ),
    ],
    ids=['original-bytes', 'different-formatting'],
)
async def test_hash_identifies_decoded_bytes(
    loader: ModuleType, tmp_path: Path, text: str, digest: str
) -> None:
    result = await loader.load_quality_document(write_document(tmp_path, text))

    assert result.sha256 == digest
    assert result.document.sources[0].id == 'public-en'


async def test_loading_keeps_answer_text_and_unknown_id(
    loader: ModuleType, tmp_path: Path
) -> None:
    payload = corpus_payload()
    answer = payload['cases'][0]['observation']['answer']
    answer.update(
        customer_reply='  Zeolite Powder\n\n',
        upsell_hint='',
        upsell_product_id='not-a-catalogue-product',
    )
    path = write_document(tmp_path, json.dumps(payload))
    result = await loader.load_quality_document(path)
    loaded = result.document.cases[0].observation.answer

    assert loaded.customer_reply == '  Zeolite Powder\n\n'
    assert loaded.upsell_hint == ''
    assert loaded.upsell_product_id == 'not-a-catalogue-product'


async def test_document_uses_completed_reader_snapshot(
    loader: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_document(tmp_path, RAW)
    returned = RAW.replace('"id":"public-en"', '"id":"reader-only-source"').encode()

    def read_snapshot(target: Path) -> bytes:
        """Supply a distinct snapshot."""
        return returned

    monkeypatch.setattr(loader, 'read_quality_bytes', read_snapshot)
    result = await loader.load_quality_document(path)

    assert result.document.sources[0].id == 'reader-only-source'
    assert (
        result.sha256
        == 'b080f8a1813f663c16e660fd6634069190825d8684e343fa115d7b160d41ec2d'
    )


# === Decoding and structure ===


@pytest.mark.parametrize(
    ('raw', 'code'),
    [
        (b'\xff', 'encoding'),
        ('', 'json_syntax'),
        ('{} {}', 'json_syntax'),
        ('null', 'schema'),
        ('[]', 'schema'),
        ('1', 'schema'),
        ('true', 'schema'),
        ('{"a":NaN}', 'nonfinite_number'),
        ('{"a":Infinity}', 'nonfinite_number'),
        ('{"a":-Infinity}', 'nonfinite_number'),
        ('{"outer":[{"inner":NaN}]}', 'nonfinite_number'),
        (
            RAW.replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
            'duplicate_key',
        ),
        (
            RAW.replace('"id":"public-en"', '"id":"public-en","id":"public-en"'),
            'duplicate_key',
        ),
    ],
    ids=[
        'encoding',
        'empty',
        'trailing-object',
        'null-root',
        'list-root',
        'number-root',
        'bool-root',
        'nan',
        'infinity',
        'negative-infinity',
        'nested-nonfinite',
        'root-duplicate',
        'nested-identical-duplicate',
    ],
)
async def test_bad_document_has_typed_code(
    loader: ModuleType, tmp_path: Path, raw: str | bytes, code: str
) -> None:
    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(write_document(tmp_path, raw))

    assert caught.value.code == code


@pytest.mark.parametrize(
    ('value', 'code'),
    [(True, 'schema'), (1.0, 'schema'), ('1', 'schema'), (2, 'unsupported_version')],
    ids=['bool', 'float', 'string', 'unsupported-integer'],
)
async def test_version_keeps_lexical_type(
    loader: ModuleType, tmp_path: Path, value: Any, code: str
) -> None:
    payload = source_payload()
    payload['schema_version'] = value

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    assert caught.value.code == code


@pytest.mark.parametrize('defect', ['missing-nullable', 'nested-extra', 'wrong-enum'])
async def test_nested_schema_is_enforced(
    loader: ModuleType, tmp_path: Path, defect: str
) -> None:
    payload = corpus_payload()
    label = payload['cases'][0]['label']
    if defect == 'missing-nullable':
        del label['reviewed_by']
    elif defect == 'nested-extra':
        label['unexpected'] = HIDDEN
    else:
        label['status'] = 'automatically-approved'

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    assert caught.value.code == 'schema'


# === File boundary ===


@pytest.mark.parametrize('value', [True, 0.0, '0'], ids=['bool', 'float', 'string'])
async def test_nested_index_keeps_lexical_type(
    loader: ModuleType, tmp_path: Path, value: Any
) -> None:
    payload = json.loads((DATA / 'facts.json').read_text())
    payload['products'][0]['facts'][0]['evidence'][0]['start'] = value

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    assert caught.value.code == 'schema'


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('max_output_tokens', 0),
        ('attempts', 0),
        ('input_tokens', -1),
        ('output_tokens', -1),
    ],
    ids=['zero-cap', 'zero-attempts', 'negative-input', 'negative-output'],
)
async def test_generation_bounds_are_enforced(
    loader: ModuleType, tmp_path: Path, field: str, value: int
) -> None:
    payload = generation_payload()
    payload['cases'][0]['answer_origin']['generation'][field] = value

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    assert caught.value.code == 'schema'


async def test_generation_boundary_values_remain_data(
    loader: ModuleType, tmp_path: Path
) -> None:
    result = await loader.load_quality_document(
        write_document(tmp_path, json.dumps(generation_payload()))
    )
    generation = result.document.cases[0].answer_origin.generation

    assert generation.max_output_tokens == 1
    assert generation.attempts == 1
    assert generation.input_tokens == 0
    assert generation.output_tokens == 0


async def test_negative_evidence_offset_is_rejected(
    loader: ModuleType, tmp_path: Path
) -> None:
    payload = json.loads((DATA / 'facts.json').read_text())
    payload['products'][0]['facts'][0]['evidence'][0]['start'] = -1

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    assert caught.value.code == 'schema'


@pytest.mark.parametrize(
    ('raw', 'code'),
    [
        ('{"' + HIDDEN + '":1,"' + HIDDEN + '":1}', 'duplicate_key'),
        ('{"secret":"' + HIDDEN + '","outer":[NaN]}', 'nonfinite_number'),
        ('{"secret":"' + HIDDEN + '"} trailing', 'json_syntax'),
        (b'{"secret":"' + HIDDEN.encode() + b'","bad":"\xff"}', 'encoding'),
    ],
    ids=['duplicate-key', 'nonfinite', 'syntax', 'encoding'],
)
async def test_decoding_failures_do_not_expose_input(
    loader: ModuleType,
    tmp_path: Path,
    raw: str | bytes,
    code: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(write_document(tmp_path, raw))

    captured = capsys.readouterr()
    assert caught.value.code == code
    assert HIDDEN not in str(caught.value)
    assert HIDDEN not in ''.join(traceback.format_exception(caught.value))
    assert HIDDEN not in captured.out + captured.err + caplog.text


async def test_input_values_stay_out_of_errors_and_logs(
    loader: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    payload = source_payload()
    payload['sources'][0]['language'] = HIDDEN

    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(
            write_document(tmp_path, json.dumps(payload))
        )

    captured = capsys.readouterr()
    assert caught.value.code == 'schema'
    assert HIDDEN not in str(caught.value)
    assert HIDDEN not in ''.join(traceback.format_exception(caught.value))
    assert HIDDEN not in captured.out + captured.err + caplog.text


async def test_read_failure_has_safe_code(
    loader: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    path = write_document(tmp_path, RAW)

    calls: list[int] = []

    def fail_read(target: Path) -> bytes:
        """Simulate a denied read."""
        calls.append(1)
        raise PermissionError(HIDDEN)

    monkeypatch.setattr(loader, 'read_quality_bytes', fail_read)
    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_document(path)

    captured = capsys.readouterr()
    assert caught.value.code == 'read_error'
    assert calls == [1]
    assert HIDDEN not in str(caught.value)
    assert HIDDEN not in ''.join(traceback.format_exception(caught.value))
    assert HIDDEN not in captured.out + captured.err + caplog.text


async def test_file_read_runs_once_outside_event_loop(
    loader: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_document(tmp_path, RAW)
    loop_thread = threading.get_ident()
    original = loader.read_quality_bytes
    off_loop: list[bool] = []

    def observe_read(target: Path) -> bytes:
        """Observe actual file reads."""
        off_loop.append(threading.get_ident() != loop_thread)
        result = original(target)
        assert isinstance(result, bytes)
        return result

    monkeypatch.setattr(loader, 'read_quality_bytes', observe_read)
    result = await loader.load_quality_document(path)

    assert result.document.sources[0].id == 'public-en'
    assert off_loop == [True]
