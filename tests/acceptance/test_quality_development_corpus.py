"""Acceptance for issue 64."""

import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

# === Data ===

ROOT = Path(__file__).parents[2]
DATA = ROOT / 'evals' / 'quality' / 'v1'
FAMILIES = (
    'price_currency',
    'form_quantity',
    'product_relations',
    'unsupported_facts',
    'completeness_hint',
)
DISCLOSED = (
    'Zeolite Powder costs 18.00 USD.',
    'Zeolite Powder costs 20.00 USD.',
    'Zeolite Powder comes as a powder in a 200 g jar.',
    'Zeolite Powder comes as a powder in a 500 g jar.',
    'Ручная кофемолка перемалывает 30 г за раз.',
    'Ручная кофемолка перемалывает 60 г за раз.',
    'Zeolite Powder pairs with Measuring Spoon.',
    'Measuring Spoon pairs with Zeolite Powder.',
    'I do not have information about delivery to Atlantis or delivery times. '
    'I can pass the question to a manager.',
    'We deliver to Atlantis within two days.',
    'В базе нет информации о доставке в Атлантиду и сроках. '
    'Могу передать вопрос менеджеру.',
    'У нас есть доставка в Атлантиду.',
    'В базе нет информации о наличии Бразилия Сантос.',
    'Бразилия Сантос есть в наличии.',
    'Hello!',
)

# === Fixtures and helpers ===


@pytest.fixture
def loader() -> ModuleType:
    """Import the package loader."""
    return importlib.import_module('reply_assistant.quality_corpus')


def questions_payload() -> dict[str, Any]:
    """Read the development questions."""
    text = (DATA / 'questions.json').read_text(encoding='utf-8')
    return cast(dict[str, Any], json.loads(text))


def corpus_payload() -> dict[str, Any]:
    """Read the development corpus."""
    text = (DATA / 'development.json').read_text(encoding='utf-8')
    return cast(dict[str, Any], json.loads(text))


async def load_package(loader: ModuleType) -> Any:
    """Load the public development package."""
    return await loader.load_quality_package(
        ROOT,
        DATA / 'sources.json',
        DATA / 'facts.json',
        DATA / 'questions.json',
        [DATA / 'development.json'],
    )


# === Package and composition ===


async def test_development_package_loads_end_to_end(loader: ModuleType) -> None:
    package = await load_package(loader)
    corpus = corpus_payload()

    assert len(package.cases) == 40
    assert corpus['partition'] == 'development'
    assert {item.case.id for item in package.cases} == {
        cast(str, entry['id']) for entry in corpus['cases']
    }


async def test_development_composition_matrix(loader: ModuleType) -> None:
    package = await load_package(loader)
    languages = [item.assessment.question.language for item in package.cases]
    families = [item.case.categories[0] for item in package.cases]
    groups: dict[str, set[str]] = {}
    for item in package.cases:
        members = groups.setdefault(item.case.group_id, set())
        members.add(item.case.label.proposed_verdict)

    assert languages.count('en') == 20
    assert languages.count('ru') == 20
    assert all(families.count(name) == 8 for name in FAMILIES)
    assert len(groups) == 20
    assert all(members == {'correct', 'incorrect'} for members in groups.values())
    assert all(len(item.case.categories) == 1 for item in package.cases)


async def test_development_labels_are_pending_proposals(loader: ModuleType) -> None:
    package = await load_package(loader)

    for item in package.cases:
        label = item.case.label
        assert label.status == 'pending'
        assert label.verdict is None
        assert label.reviewed_by is None
        assert label.reviewed_at is None
        assert label.confirmation_ref is None
        assert label.proposed_verdict in ('correct', 'incorrect')
        assert bool(label.rationale)


async def test_questions_precede_answers(loader: ModuleType) -> None:
    package = await load_package(loader)
    questions = questions_payload()
    usage: dict[str, int] = {}
    for item in package.cases:
        usage[item.case.question_id] = usage.get(item.case.question_id, 0) + 1

    assert len(questions['questions']) == 20
    assert {cast(str, q['id']) for q in questions['questions']} == set(usage)
    assert sorted(usage.values()) == [2] * 20
    assert all(bool(cast(str, q['basis'])) for q in questions['questions'])


async def test_disclosed_examples_stay_in_development(loader: ModuleType) -> None:
    package = await load_package(loader)
    replies = [item.case.observation.answer.customer_reply for item in package.cases]

    for text in DISCLOSED:
        assert text in replies


async def test_public_artifacts_hold_no_holdout(loader: ModuleType) -> None:
    await load_package(loader)

    assert corpus_payload()['partition'] == 'development'
    assert not any('holdout' in path.name.lower() for path in DATA.rglob('*'))
