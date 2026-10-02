"""Quality report unit tests."""

import json
from typing import Any

from reply_assistant.quality_report import (
    CaseEntry,
    CaseOutcome,
    ReportMeta,
    acceptance_gate,
    build_report,
    compute_metrics,
    render_json,
    render_markdown,
)

# === Fixtures and helpers ===


def outcome(**changes: Any) -> CaseOutcome:
    """Build one case outcome."""

    base: dict[str, Any] = {
        'execution_status': 'evaluated',
        'factual_verdict': 'confirmed',
        'human_status': 'confirmed',
        'human_verdict': 'correct',
        'language': 'en',
        'independent': True,
    }
    base.update(changes)
    return CaseOutcome(**base)


def readiness_set(manual: int = 0) -> list[CaseOutcome]:
    """Build a structurally ready set."""

    outcomes: list[CaseOutcome] = []
    outcomes.extend(outcome() for _ in range(10 - manual))
    outcomes.extend(
        outcome(
            factual_verdict='error',
            human_verdict='incorrect',
            language='ru',
        )
        for _ in range(10)
    )
    outcomes.extend(outcome(factual_verdict='manual_review') for _ in range(manual))
    return outcomes


# === Metrics ===


def test_failed_statuses_and_their_verdicts_stay_out_of_quality_rates() -> None:
    metrics = compute_metrics(
        [
            outcome(execution_status='evaluator_error', factual_verdict='error'),
            outcome(
                execution_status='invalid_input',
                factual_verdict='confirmed',
                human_verdict='incorrect',
            ),
            outcome(factual_verdict='error'),
        ]
    )

    assert metrics.failures == 2
    assert metrics.evaluated == 1
    assert metrics.error == 1
    assert metrics.confirmed == 0
    assert metrics.c_size == 1
    assert metrics.w_size == 0
    assert metrics.false_confirmation_rate is None
    assert metrics.false_rejection_rate == 1.0


def test_metrics_on_an_empty_set_divide_by_zero_nowhere() -> None:
    metrics = compute_metrics([])

    assert metrics.total == 0
    assert metrics.evaluated == 0
    assert metrics.failures == 0
    assert metrics.manual_share is None
    assert metrics.false_confirmation_rate is None
    assert metrics.false_rejection_rate is None


# === Readiness ===


def test_gate_names_every_structural_violation() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(human_verdict='unresolved', language='ru')

    readiness = acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('correct' in reason for reason in readiness.reasons)
    assert any('language' in reason for reason in readiness.reasons)


def test_evaluated_outcomes_without_a_verdict_never_reach_thresholds() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(factual_verdict=None)

    readiness = acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('no factual verdict' in reason for reason in readiness.reasons)


def test_gate_names_a_stray_verdict_on_a_not_evaluated_outcome() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(
        execution_status='recorded_failure',
        factual_verdict='confirmed',
    )

    readiness = acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('but carry a verdict' in reason for reason in readiness.reasons)


def test_missing_independence_evidence_is_contamination() -> None:
    outcomes = readiness_set()
    outcomes[0] = CaseOutcome(
        execution_status='evaluated',
        factual_verdict='confirmed',
        human_status='confirmed',
        human_verdict='correct',
        language='en',
    )

    readiness = acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('contaminated' in reason for reason in readiness.reasons)


def test_gate_names_every_threshold_violation() -> None:
    outcomes = readiness_set(manual=5)
    outcomes[0] = outcome(factual_verdict='error')
    outcomes[10] = outcome(
        factual_verdict='confirmed',
        human_verdict='incorrect',
        language='ru',
    )

    readiness = acceptance_gate(outcomes)

    assert readiness.state == 'fail_'
    assert any('confirmation' in reason for reason in readiness.reasons)
    assert any('rejection' in reason for reason in readiness.reasons)
    assert any('manual' in reason for reason in readiness.reasons)


# === Renderers ===


def report_meta() -> ReportMeta:
    """Build one report meta."""

    return ReportMeta(
        rules_id='factual-assessment-v1',
        rules_sha256='a' * 64,
        sources=[('kb/example-en.yaml', 'b' * 64)],
    )


def case_entry(**changes: Any) -> CaseEntry:
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
    return CaseEntry(**base)


def test_markdown_repeats_the_rules_and_source_versions() -> None:
    markdown = render_markdown(build_report(report_meta(), [case_entry()]))

    assert 'factual-assessment-v1' in markdown
    assert 'a' * 64 in markdown
    assert 'kb/example-en.yaml' in markdown
    assert 'b' * 64 in markdown


def test_absolute_source_paths_publish_only_pinned_forms() -> None:
    entries = [
        case_entry(
            case_id='case-local',
            source_path='/workspace/reply-assistant/kb/example-en.yaml',
        ),
        case_entry(case_id='case-unknown', source_path='/elsewhere/other.yaml'),
    ]

    payload = json.loads(render_json(build_report(report_meta(), entries)))

    assert payload['cases'][0]['source_path'] == 'kb/example-en.yaml'
    assert payload['cases'][1]['source_path'] is None


def test_markdown_keeps_a_verdict_line_without_a_verdict() -> None:
    report = build_report(
        report_meta(),
        [case_entry(execution_status='recorded_failure', factual_verdict=None)],
    )

    assert 'Verdict: null' in render_markdown(report)
