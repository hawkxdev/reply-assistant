"""Quality report metrics tests."""

from typing import Any

from reply_assistant.quality_report import CaseOutcome, acceptance_gate, compute_metrics

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
