"""Quality document loading tests."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from reply_assistant.quality_corpus import (
    QualityInputError,
    load_quality_document,
    load_quality_package,
)

DATA = Path(__file__).parents[1] / 'evals' / 'quality' / 'v1'
ROOT = Path(__file__).parents[1]
ZERO = '0' * 64


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


# === Package helpers ===


def package_payload(relative: str) -> dict[str, Any]:
    """Read one supplied package payload."""
    text = (DATA / relative).read_text(encoding='utf-8')
    return cast(dict[str, Any], json.loads(text))


def question_digest(question: dict[str, Any]) -> str:
    """Hash one question payload."""
    encoded = json.dumps(
        question,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def write_json(folder: Path, name: str, payload: dict[str, Any]) -> str:
    """Write one package document."""
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    (folder / name).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_package(
    folder: Path,
    sources: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
    questions: dict[str, Any] | None = None,
    corpora: list[dict[str, Any]] | None = None,
    with_catalogues: bool = True,
) -> tuple[Path, Path, Path, list[Path]]:
    """Write one consistent package."""
    if with_catalogues:
        catalogue_folder = folder / 'kb'
        catalogue_folder.mkdir()
        for name in ('example-en.yaml', 'example-ru.yaml'):
            (catalogue_folder / name).write_bytes((ROOT / 'kb' / name).read_bytes())
    if sources is None:
        sources = package_payload('sources.json')
    if facts is None:
        facts = package_payload('facts.json')
    if questions is None:
        questions = package_payload('examples/questions.json')
    if corpora is None:
        corpora = [package_payload('examples/corpus-valid.json')]
    sources_digest = write_json(folder, 'sources.json', sources)
    facts['sources_sha256'] = sources_digest
    facts_digest = write_json(folder, 'facts.json', facts)
    questions['sources_sha256'] = sources_digest
    questions_digest = write_json(folder, 'questions.json', questions)
    question_hashes = {
        cast(str, question['id']): question_digest(question)
        for question in questions['questions']
    }
    corpus_paths = []
    for index, corpus in enumerate(corpora):
        corpus['sources_sha256'] = sources_digest
        corpus['facts_sha256'] = facts_digest
        corpus['questions_sha256'] = questions_digest
        for case in corpus['cases']:
            case['question_sha256'] = question_hashes.get(
                cast(str, case['question_id']), ZERO
            )
        write_json(folder, f'corpus-{index}.json', corpus)
        corpus_paths.append(folder / f'corpus-{index}.json')
    return (
        folder / 'sources.json',
        folder / 'facts.json',
        folder / 'questions.json',
        corpus_paths,
    )


async def package_error(
    paths: tuple[Path, Path, Path, list[Path]],
) -> QualityInputError:
    """Load one package expecting failure."""
    sources, facts, questions, corpora = paths
    with pytest.raises(QualityInputError) as caught:
        await load_quality_package(sources.parent, sources, facts, questions, corpora)
    return caught.value


# === Package loading ===


async def test_wrong_document_kind_in_slot_is_rejected(tmp_path: Path) -> None:
    corpus = package_payload('examples/corpus-valid.json')
    paths = build_package(tmp_path, facts=corpus)

    assert (await package_error(paths)).code == 'schema'


async def test_catalogue_language_mismatch_fails(tmp_path: Path) -> None:
    sources = package_payload('sources.json')
    sources['sources'][0]['language'] = 'ru'
    paths = build_package(tmp_path, sources=sources)

    assert (await package_error(paths)).code == 'source_hash'


async def test_missing_catalogue_fails_with_read_error(tmp_path: Path) -> None:
    paths = build_package(tmp_path, with_catalogues=False)

    assert (await package_error(paths)).code == 'read_error'


async def test_supported_annotation_without_fact_fails(tmp_path: Path) -> None:
    facts = package_payload('facts.json')
    powder = facts['products'][0]
    support = next(
        item
        for item in powder['predicate_support']
        if item['predicate'] == 'object_mass'
    )
    support['status'] = 'supported'
    paths = build_package(tmp_path, facts=facts)

    assert (await package_error(paths)).code == 'inconsistent_fact'


async def test_absent_annotation_with_fact_fails(tmp_path: Path) -> None:
    facts = package_payload('facts.json')
    powder = facts['products'][0]
    powder['predicate_support'].append(
        {'predicate': 'name', 'status': 'absent', 'reason': 'checked absence'}
    )
    paths = build_package(tmp_path, facts=facts)

    assert (await package_error(paths)).code == 'inconsistent_fact'


async def test_unknown_annotated_product_fails(tmp_path: Path) -> None:
    facts = package_payload('facts.json')
    facts['products'][0]['product_id'] = 'ghost-product'
    paths = build_package(tmp_path, facts=facts)

    assert (await package_error(paths)).code == 'unknown_reference'
