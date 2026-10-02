"""Acceptance for issue 84."""

import json
import re
from typing import Any

import pytest

from reply_assistant.quality_report import CaseOutcome

# === Fixtures and helpers ===


@pytest.fixture
def report_module() -> Any:
    """Import the report module."""
    import importlib

    return importlib.import_module('reply_assistant.quality_report')


def meta(report_module: Any) -> Any:
    """Build one report meta."""
    return report_module.ReportMeta(
        rules_id='factual-assessment-v1',
        rules_sha256='a' * 64,
        sources=[('kb/example-en.yaml', 'b' * 64)],
    )


def entry(**changes: Any) -> Any:
    """Build one case entry."""
    base: dict[str, Any] = {
        'case_id': 'case-en-1',
        'language': 'en',
        'source_path': 'kb/example-en.yaml',
        'question': 'How much does Zeolite Powder cost?',
        'answer': 'Zeolite Powder costs 18.00 USD.',
        'execution_status': 'evaluated',
        'factual_verdict': 'confirmed',
        'human_status': 'confirmed',
        'human_verdict': 'correct',
        'grounds': (),
        'unresolved': (),
    }
    base.update(changes)
    return report_module_stub().CaseEntry(**base)


def report_module_stub() -> Any:
    """Import the report module."""
    import importlib

    return importlib.import_module('reply_assistant.quality_report')


# === Structure ===


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_json_carries_identity_and_summary(report_module: Any) -> None:
    report = report_module.build_report(
        meta(report_module), [entry(), entry(case_id='case-en-2')]
    )
    payload = json.loads(report_module.render_json(report))

    assert payload['report_kind'] == 'quality-evaluation'
    assert payload['schema_version'] == 1
    assert payload['rules_id'] == 'factual-assessment-v1'
    assert payload['rules_sha256'] == 'a' * 64
    assert payload['sources'] == [['kb/example-en.yaml', 'b' * 64]]
    assert payload['summary']['total'] == 2
    assert payload['summary']['confirmed'] == 2
    first = payload['cases'][0]
    assert first['source_path'] == 'kb/example-en.yaml'
    assert first['question'] == 'How much does Zeolite Powder cost?'
    assert first['answer'] == 'Zeolite Powder costs 18.00 USD.'
    assert first['language'] == 'en'
    assert [case['case_id'] for case in payload['cases']] == [
        'case-en-1',
        'case-en-2',
    ]


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_markdown_agrees_with_json(report_module: Any) -> None:
    report = report_module.build_report(
        meta(report_module),
        [
            entry(),
            entry(
                case_id='case-ru-1',
                language='ru',
                source_path='kb/example-ru.yaml',
                factual_verdict='error',
                human_verdict='incorrect',
                grounds=('price_mismatch:990 RUB',),
            ),
        ],
    )
    markdown = report_module.render_markdown(report)
    payload = json.loads(report_module.render_json(report))

    assert 'quality-evaluation' in markdown
    sections = {}
    for chunk in markdown.split('### ')[1:]:
        case_id = chunk.splitlines()[0].split(' ')[0]
        sections[case_id] = chunk
    for case in payload['cases']:
        assert case['case_id'] in markdown
        assert case['factual_verdict'] in markdown
        section = sections[case['case_id']]
        assert f'Verdict: {case["factual_verdict"]}' in section
        for ground in case['grounds']:
            assert ground in section
        for reason in case['unresolved']:
            assert reason in section
    summary_section = markdown.split('## Summary')[1].split('## Cases')[0]
    assert str(payload['summary']['total']) in summary_section
    assert str(payload['summary']['error']) in summary_section


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_renders_are_deterministic_and_ordered(report_module: Any) -> None:
    entries = [entry(), entry(case_id='case-en-2'), entry(case_id='case-en-3')]
    first = report_module.build_report(meta(report_module), entries)
    second = report_module.build_report(meta(report_module), entries)

    assert report_module.render_json(first) == report_module.render_json(second)
    assert report_module.render_markdown(first) == report_module.render_markdown(second)
    payload = json.loads(report_module.render_json(first))
    assert [case['case_id'] for case in payload['cases']] == [
        'case-en-1',
        'case-en-2',
        'case-en-3',
    ]


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_grounds_and_uncertainty_are_reported(report_module: Any) -> None:
    report = report_module.build_report(
        meta(report_module),
        [
            entry(
                factual_verdict='manual_review',
                grounds=(),
                unresolved=('remainder:0:10',),
            )
        ],
    )
    payload = json.loads(report_module.render_json(report))

    assert payload['cases'][0]['unresolved'] == ['remainder:0:10']
    assert 'remainder:0:10' in report_module.render_markdown(report)


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_label_state_is_reported(report_module: Any) -> None:
    report = report_module.build_report(
        meta(report_module),
        [entry(human_status='pending', human_verdict=None)],
    )
    payload = json.loads(report_module.render_json(report))

    assert payload['cases'][0]['human_status'] == 'pending'
    assert payload['cases'][0]['human_verdict'] is None
    assert 'pending' in report_module.render_markdown(report)


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_failures_are_separated_from_evaluated(report_module: Any) -> None:
    report = report_module.build_report(
        meta(report_module),
        [
            entry(execution_status='recorded_failure', factual_verdict=None),
            entry(),
        ],
    )
    payload = json.loads(report_module.render_json(report))

    assert payload['summary']['evaluated'] == 1
    assert payload['summary']['failures'] == 1


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_no_timestamps_or_absolute_paths(report_module: Any) -> None:
    leak_entry = report_module.CaseEntry(
        case_id='case-abs',
        language='en',
        source_path='/workspace/reply-assistant/kb/example-en.yaml',
        question='How much does Zeolite Powder cost?',
        answer='Zeolite Powder costs 18.00 USD.',
        execution_status='evaluated',
        factual_verdict='confirmed',
        human_status='confirmed',
        human_verdict='correct',
        grounds=(),
        unresolved=(),
    )
    leak_report = report_module.build_report(meta(report_module), [leak_entry])
    rendered = report_module.render_json(leak_report) + report_module.render_markdown(
        leak_report
    )

    assert '/Users/' not in rendered
    assert '/workspace/reply-assistant' not in rendered
    assert not re.search(r'\d{4}-\d{2}-\d{2}', rendered)


# === Restricted content ===


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_restricted_content_stays_out(report_module: Any) -> None:
    entry = report_module.CaseEntry(
        case_id='case-secret',
        language='en',
        source_path='kb/example-en.yaml',
        question='How much does Zeolite Powder cost?',
        answer='Zeolite Powder costs 18.00 USD.',
        execution_status='evaluated',
        factual_verdict='confirmed',
        human_status='confirmed',
        human_verdict='correct',
        grounds=(),
        unresolved=(),
    )
    report = report_module.build_report(meta(report_module), [entry])
    rendered = report_module.render_json(report)

    assert 'api-key' not in rendered
    assert 'REPLY_ASSISTANT' not in rendered


@pytest.mark.xfail(strict=True, reason='E11 not implemented')
def test_outcome_mapping_matches_e10(report_module: Any) -> None:
    entries = [
        entry(),
        entry(
            case_id='case-ru-1',
            language='ru',
            factual_verdict='error',
            human_verdict='incorrect',
        ),
        entry(
            case_id='case-failed',
            execution_status='recorded_failure',
            factual_verdict=None,
            human_status='pending',
            human_verdict=None,
        ),
    ]
    report = report_module.build_report(meta(report_module), entries)
    outcomes = [
        CaseOutcome(
            execution_status=case['execution_status'],
            factual_verdict=case['factual_verdict'],
            human_status=case['human_status'],
            human_verdict=case['human_verdict'],
            language=case['language'],
        )
        for case in json.loads(report_module.render_json(report))['cases']
    ]
    direct = report_module.compute_metrics(outcomes)

    assert report.summary == direct
    rendered_summary = json.loads(report_module.render_json(report))['summary']
    assert rendered_summary == {
        'total': direct.total,
        'evaluated': direct.evaluated,
        'confirmed': direct.confirmed,
        'error': direct.error,
        'manual_review': direct.manual_review,
        'failures': direct.failures,
        'c_size': direct.c_size,
        'w_size': direct.w_size,
        'false_confirmation_rate': direct.false_confirmation_rate,
        'false_rejection_rate': direct.false_rejection_rate,
        'manual_share': direct.manual_share,
        'pending_references': direct.pending_references,
        'disputed_references': direct.disputed_references,
        'unresolved_references': direct.unresolved_references,
    }
