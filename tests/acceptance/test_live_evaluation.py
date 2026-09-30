"""Acceptance for issue 51."""

import importlib
import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx2
import pytest
from pydantic import ValidationError

from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import (
    Completion,
    OpenAICompatibleClient,
    ProviderError,
    Usage,
)
from reply_assistant.settings import Settings

pytestmark = pytest.mark.xfail(strict=True, reason='issue 51 is not implemented')

# === Data ===

ROOT = Path(__file__).parents[2]
KB_FILE = ROOT / 'kb' / 'example-en.yaml'
MESSAGES = [
    'What is the price and form of Zeolite Powder?',
    'Do you deliver to Atlantis, and how long does it take?',
    'Will Zeolite Powder cure my spring allergy?',
]
ANSWERS: list[dict[str, Any]] = [
    {
        'customer_reply': 'Zeolite Powder: powder, 200 g jar, 18.00 USD.',
        'upsell_product_id': 'measuring-spoon',
        'upsell_hint': 'Offer the Measuring Spoon for one serving.',
        'kb_match': 'found',
    },
    {
        'customer_reply': 'No delivery information is available. Ask the manager.',
        'upsell_product_id': None,
        'upsell_hint': '',
        'kb_match': 'none',
    },
    {
        'customer_reply': 'This is a food supplement. Ask a doctor about allergies.',
        'upsell_product_id': None,
        'upsell_hint': '',
        'kb_match': 'partial',
    },
]
PRIMARY: dict[str, Any] = {
    'provider_api_key': 'test-key',
    'provider_base_url': 'https://primary.test/v1',
    'provider_model': 'model-test',
    'kb_path': KB_FILE,
}
SECONDARY: dict[str, Any] = {
    'fallback_provider_api_key': 'second-key',
    'fallback_provider_base_url': 'https://second.test/v1',
    'fallback_provider_model': 'second-model',
}
HIDDEN = 'private-exception-details-51'
CAVEAT = (
    'Manual fact review is required; passing checks do not prove factual grounding.'
)

# === Helpers ===


class ScriptedClient:
    """Record completions and shutdown."""

    def __init__(self, outcomes: Sequence[dict[str, Any] | Exception]) -> None:
        """Keep the scripted outcomes."""
        self.outcomes = list(outcomes)
        self.messages: list[list[dict[str, str]]] = []
        self.closes = 0

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return the next outcome."""
        self.messages.append(messages)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Completion(json.dumps(outcome), Usage(10, 5, 'fake'))

    async def aclose(self) -> None:
        """Record one owned shutdown."""
        self.closes += 1


@pytest.fixture
async def kb() -> KnowledgeBase:
    """Load the public example."""
    return await load_knowledge_base(KB_FILE)


@pytest.fixture
def evaluation() -> ModuleType:
    """Import the evaluation module."""
    return importlib.import_module('reply_assistant.evaluation')


def cli_module() -> ModuleType:
    """Load the live command."""
    spec = importlib.util.spec_from_file_location(
        'live_cli', ROOT / 'scripts/evaluate_live.py'
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# === Evaluation ===


async def test_public_cases_use_checked_service_in_fixed_order(
    kb: KnowledgeBase, evaluation: ModuleType
) -> None:
    model = ScriptedClient(ANSWERS)

    report = await evaluation.evaluate(kb, model)
    data = report.model_dump(mode='json')

    assert data['passed'] is True
    assert [item['id'] for item in data['cases']] == ['price', 'delivery', 'health']
    assert [item['message'] for item in data['cases']] == MESSAGES
    assert [item['passed'] for item in data['cases']] == [True, True, True]
    assert [item['failures'] for item in data['cases']] == [[], [], []]
    assert [item['error'] for item in data['cases']] == [None, None, None]
    assert len(model.messages) == 3
    assert [messages[1]['content'] for messages in model.messages] == [
        (
            '<customer_message>\nWhat is the price and form of Zeolite Powder?\n'
            '</customer_message>'
        ),
        (
            '<customer_message>\nDo you deliver to Atlantis, and how long '
            'does it take?\n</customer_message>'
        ),
        (
            '<customer_message>\nWill Zeolite Powder cure my spring allergy?\n'
            '</customer_message>'
        ),
    ]
    assert data['cases'][2]['suggestion']['customer_reply'].endswith(
        'This product is a food supplement and is not a medicine.'
    )
    assert model.closes == 0


@pytest.mark.parametrize(
    ('index', 'changes', 'failures'),
    [
        (0, {'kb_match': 'partial'}, ['kb_match']),
        (0, {'upsell_product_id': 'travel-pill-box'}, ['upsell_product_id']),
        (
            0,
            {'customer_reply': 'powder, 200 g jar, 18.00 USD.'},
            ['missing:Zeolite Powder'],
        ),
        (
            0,
            {'customer_reply': 'Zeolite Powder: 18.00 USD.'},
            ['missing:powder, 200 g jar'],
        ),
        (
            0,
            {'customer_reply': 'Zeolite Powder: powder, 200 g jar.'},
            ['missing:18.00 USD'],
        ),
        (1, {'kb_match': 'found'}, ['kb_match']),
        (1, {'upsell_product_id': 'measuring-spoon'}, ['upsell_product_id']),
        (2, {'kb_match': 'found'}, ['kb_match']),
    ],
    ids=[
        'price match',
        'price upsell',
        'name',
        'form',
        'price',
        'delivery match',
        'delivery upsell',
        'health match',
    ],
)
async def test_case_expectation_failure_is_reported(
    kb: KnowledgeBase,
    evaluation: ModuleType,
    index: int,
    changes: dict[str, Any],
    failures: list[str],
) -> None:
    answers = [dict(answer) for answer in ANSWERS]
    answers[index].update(changes)

    report = await evaluation.evaluate(kb, ScriptedClient(answers))
    data = report.model_dump(mode='json')

    assert data['passed'] is False
    assert data['cases'][index]['passed'] is False
    assert data['cases'][index]['failures'] == failures
    assert data['cases'][index]['suggestion'] is not None
    assert data['cases'][index]['error'] is None


@pytest.mark.parametrize(
    ('outcomes', 'error', 'calls'),
    [
        ([ProviderError('fake', 'timeout', HIDDEN)], 'provider_error', 3),
        ([{'bad': HIDDEN}, {'bad': HIDDEN}], 'suggestion_rejected', 4),
        ([ValueError(HIDDEN)], 'internal_error', 3),
    ],
    ids=['provider', 'rejected', 'unexpected'],
)
async def test_failed_case_is_safe_and_remaining_cases_run(
    kb: KnowledgeBase,
    evaluation: ModuleType,
    capsys: pytest.CaptureFixture[str],
    outcomes: list[dict[str, Any] | Exception],
    error: str,
    calls: int,
) -> None:
    model = ScriptedClient([*outcomes, *ANSWERS[1:]])

    report = await evaluation.evaluate(kb, model)
    data = report.model_dump(mode='json')
    captured = capsys.readouterr()

    assert data['passed'] is False
    assert data['cases'][0] == {
        'id': 'price',
        'message': MESSAGES[0],
        'passed': False,
        'failures': [],
        'suggestion': None,
        'error': error,
    }
    assert [item['passed'] for item in data['cases'][1:]] == [True, True]
    assert len(model.messages) == calls
    assert HIDDEN not in json.dumps(data)
    assert captured.out == ''
    assert captured.err == ''


# === Output cap ===


@pytest.mark.parametrize('cap', [0, -1])
def test_nonpositive_cap_is_rejected_before_transport(cap: int) -> None:
    client_class: Any = OpenAICompatibleClient
    with pytest.raises(ValidationError):
        Settings(**PRIMARY, provider_max_output_tokens=cap, _env_file=None)
    with pytest.raises(ValueError, match='positive'):
        client_class(
            base_url='https://primary.test/v1',
            api_key=Settings(**PRIMARY).provider_api_key,
            model='model-test',
            max_output_tokens=cap,
        )


@pytest.mark.parametrize('fallback', [False, True], ids=['primary', 'secondary'])
async def test_factory_applies_cap_to_the_answering_provider(fallback: bool) -> None:
    settings = Settings(
        **PRIMARY, **SECONDARY, provider_max_output_tokens=600, _env_file=None
    )
    seen: list[dict[str, Any]] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        """Capture one bounded request."""
        seen.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                'choices': [{'message': {'content': json.dumps(ANSWERS[0])}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
            },
        )

    transport = httpx2.MockTransport(answer)
    if fallback:
        cls = importlib.import_module('reply_assistant.model_client').FallbackClient
        model = cls.from_settings(
            settings,
            primary_transport=httpx2.MockTransport(
                lambda request: httpx2.Response(503)
            ),
            secondary_transport=transport,
        )
    else:
        model = OpenAICompatibleClient.from_settings(settings, transport=transport)
    try:
        await model.complete(
            [{'role': 'user', 'content': 'Price?'}], {'type': 'object'}
        )
    finally:
        await model.aclose()

    assert seen[0]['max_tokens'] == 600


# === Command ===


@pytest.mark.parametrize('passed', [True, False], ids=['passed', 'failed'])
async def test_command_writes_both_reports_and_closes_client(
    kb: KnowledgeBase,
    evaluation: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    passed: bool,
) -> None:
    cli = cli_module()
    outcomes: list[dict[str, Any] | Exception] = list(ANSWERS)
    if not passed:
        outcomes[0] = ProviderError('fake', 'timeout', HIDDEN)
    model = ScriptedClient(outcomes)
    builds: list[Settings] = []
    settings = Settings(**PRIMARY, provider_max_output_tokens=600, _env_file=None)

    def build(config: Settings) -> ScriptedClient:
        """Record the configured client."""
        builds.append(config)
        return model

    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    monkeypatch.setattr(cli.OpenAICompatibleClient, 'from_settings', build)

    code = await cli.run(tmp_path / 'report')
    data = json.loads((tmp_path / 'report/results.json').read_text(encoding='utf-8'))
    summary = (tmp_path / 'report/summary.md').read_text(encoding='utf-8')
    captured = capsys.readouterr()

    assert code == (0 if passed else 1)
    assert data['passed'] is passed
    assert [item['id'] for item in data['cases']] == ['price', 'delivery', 'health']
    assert builds == [settings]
    assert model.closes == 1
    assert all(name in summary for name in ['price', 'delivery', 'health'])
    assert CAVEAT in summary
    assert HIDDEN not in summary + captured.out + captured.err
    assert captured.out == (
        'Live evaluation passed.\n' if passed else 'Live evaluation failed.\n'
    )
    assert captured.err == ''


async def test_command_closes_client_on_writing_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    settings = Settings(**PRIMARY, _env_file=None)
    model = ScriptedClient(ANSWERS)
    destination = tmp_path / 'file'
    destination.write_text('occupied', encoding='utf-8')
    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    monkeypatch.setattr(
        cli.OpenAICompatibleClient, 'from_settings', lambda config: model
    )

    code = await cli.run(destination)
    captured = capsys.readouterr()

    assert code == 1
    assert model.closes == 1
    assert captured.out == 'Live evaluation failed.\n'
    assert captured.err == ''


def test_command_entrypoint_accepts_output_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = cli_module()
    calls: list[Path] = []

    async def run(destination: Path) -> int:
        """Record the requested directory."""
        calls.append(destination)
        return 1

    monkeypatch.setattr(cli, 'run', run)
    monkeypatch.setattr('sys.argv', ['evaluate_live.py', '--output-dir', str(tmp_path)])

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 1
    assert calls == [tmp_path]


async def test_alternative_supported_outputs_pass(
    kb: KnowledgeBase, evaluation: ModuleType
) -> None:
    answers = [dict(answer) for answer in ANSWERS]
    answers[0]['upsell_product_id'] = 'zeolite-capsules-90'
    answers[2]['kb_match'] = 'none'

    report = await evaluation.evaluate(kb, ScriptedClient(answers))

    assert report.passed is True


async def test_every_failed_condition_is_kept_in_order(
    kb: KnowledgeBase, evaluation: ModuleType
) -> None:
    answers = [dict(answer) for answer in ANSWERS]
    answers[0].update(
        customer_reply='Ask a manager.', kb_match='none', upsell_product_id=None
    )

    report = await evaluation.evaluate(kb, ScriptedClient(answers))

    assert report.cases[0].failures == [
        'kb_match',
        'upsell_product_id',
        'missing:Zeolite Powder',
        'missing:powder, 200 g jar',
        'missing:18.00 USD',
    ]


async def test_command_builds_the_configured_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = cli_module()
    settings = Settings(**PRIMARY, **SECONDARY, _env_file=None)
    model = ScriptedClient(ANSWERS)
    built: list[Settings] = []

    def build(config: Settings) -> ScriptedClient:
        """Record the fallback factory."""
        built.append(config)
        return model

    def refuse(config: Settings) -> ScriptedClient:
        """Refuse primary only construction."""
        raise AssertionError('fallback was ignored')

    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    monkeypatch.setattr(cli.FallbackClient, 'from_settings', build)
    monkeypatch.setattr(cli.OpenAICompatibleClient, 'from_settings', refuse)

    code = await cli.run(tmp_path)

    assert code == 0
    assert built == [settings]
    assert model.closes == 1


async def test_command_hides_setup_failure_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()

    def fail() -> Settings:
        """Reject the command setup."""
        raise ValueError(HIDDEN)

    monkeypatch.setattr(cli, 'Settings', fail)

    code = await cli.run(tmp_path)
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == 'Live evaluation failed.\n'
    assert captured.err == ''
