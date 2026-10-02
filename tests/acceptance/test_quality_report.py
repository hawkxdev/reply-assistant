"""Acceptance for issue 81."""

import importlib
from typing import Any

import pytest

# === Fixtures and helpers ===


def the_report() -> Any:
    """Import the report module."""
    return importlib.import_module('reply_assistant.quality_report')


def outcome(**changes: Any) -> Any:
    """Build one case outcome."""
    module = importlib.import_module('reply_assistant.quality_report')
    base: dict[str, Any] = {
        'execution_status': 'evaluated',
        'factual_verdict': 'confirmed',
        'human_status': 'confirmed',
        'human_verdict': 'correct',
        'language': 'en',
    }
    base.update(changes)
    return module.CaseOutcome(**base)


def readiness_set(manual: int = 0) -> list[Any]:
    """Build a structurally ready set."""
    outcomes: list[Any] = []
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


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_metrics_on_a_mixed_set_are_exact() -> None:
    false_rejection = outcome(factual_verdict='error')
    false_confirmation = outcome(human_verdict='incorrect', factual_verdict='confirmed')
    outcomes = [
        outcome(),
        outcome(),
        outcome(
            factual_verdict='error',
            human_verdict='incorrect',
            language='ru',
        ),
        outcome(factual_verdict='manual_review'),
        outcome(execution_status='recorded_failure', factual_verdict=None),
        false_rejection,
        false_confirmation,
    ]
    metrics = the_report().compute_metrics(outcomes)

    assert metrics.total == 7
    assert metrics.evaluated == 6
    assert metrics.confirmed == 3
    assert metrics.error == 2
    assert metrics.manual_review == 1
    assert metrics.failures == 1
    assert metrics.c_size == 4
    assert metrics.w_size == 2
    assert metrics.false_confirmation_rate == 1 / 2
    assert metrics.false_rejection_rate == 1 / 4
    assert metrics.manual_share == pytest.approx(1 / 6)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_rates_are_null_on_empty_denominators() -> None:
    report = the_report()
    en_only = report.compute_metrics([outcome()])
    ru_only = report.compute_metrics(
        [
            outcome(
                factual_verdict='error',
                human_verdict='incorrect',
                language='ru',
            )
        ]
    )

    assert en_only.w_size == 0
    assert en_only.false_confirmation_rate is None
    assert en_only.c_size == 1
    assert en_only.false_rejection_rate == 0.0
    assert ru_only.c_size == 0
    assert ru_only.false_rejection_rate is None
    assert ru_only.false_confirmation_rate == 0.0
    assert ru_only.manual_share == 0.0


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_execution_failure_never_enters_the_rates() -> None:
    outcomes = [
        outcome(execution_status='recorded_failure', factual_verdict=None),
        outcome(
            factual_verdict='error',
            human_verdict='incorrect',
            language='ru',
        ),
    ]
    metrics = the_report().compute_metrics(outcomes)

    assert metrics.failures == 1
    assert metrics.evaluated == 1
    assert metrics.false_rejection_rate is None
    assert metrics.false_confirmation_rate == 0.0


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_unresolved_label_never_enters_c_or_w() -> None:
    metrics = the_report().compute_metrics(
        [outcome(factual_verdict='manual_review', human_verdict='unresolved')]
    )

    assert metrics.c_size == 0
    assert metrics.w_size == 0
    assert metrics.false_confirmation_rate is None


# === Readiness ===


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_ready_set_passes() -> None:
    readiness = the_report().acceptance_gate(readiness_set())

    assert readiness.state == 'pass_'
    assert readiness.reasons == ()


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_empty_set_is_not_ready() -> None:
    readiness = the_report().acceptance_gate([])

    assert readiness.state == 'not_ready'
    assert any('expected 20 outcomes' in reason for reason in readiness.reasons)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_fifth_manual_case_fails_readiness() -> None:
    readiness = the_report().acceptance_gate(readiness_set(manual=5))

    assert readiness.state == 'fail_'
    assert any('manual' in reason for reason in readiness.reasons)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_truth_imbalance_blocks_readiness() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(human_verdict='incorrect')

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('correct' in reason for reason in readiness.reasons)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_language_imbalance_blocks_readiness() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(language='ru')

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'
    assert any('language' in reason for reason in readiness.reasons)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_unresolved_reference_blocks_readiness() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(human_verdict='unresolved')

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_pending_reference_blocks_readiness() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(human_status='pending', human_verdict=None)

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_false_confirmation_fails_readiness() -> None:
    outcomes = readiness_set()
    outcomes[10] = outcome(
        factual_verdict='confirmed',
        human_verdict='incorrect',
        language='ru',
    )

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'fail_'
    assert any('confirmation' in reason for reason in readiness.reasons)


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_execution_failure_blocks_readiness() -> None:
    outcomes = readiness_set()
    outcomes[0] = outcome(
        execution_status='recorded_failure',
        factual_verdict=None,
    )

    readiness = the_report().acceptance_gate(outcomes)

    assert readiness.state == 'not_ready'


@pytest.mark.xfail(strict=True, reason='E10 not implemented')
def test_metrics_are_repeatable() -> None:
    outcomes = readiness_set(manual=2)

    outcomes_again = readiness_set(manual=2)
    first = the_report().compute_metrics(outcomes)
    second = the_report().compute_metrics(outcomes_again)
    assert first == second
