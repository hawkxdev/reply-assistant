"""Verify bounded recovery decisions."""

from dataclasses import replace

import pytest
from scripts.review_handoff import (
    DispatchClaim,
    DispatchState,
    ReleaseProof,
    WorkEvidence,
    dispatch_decision,
    lead_write_allowed,
    work_outcome,
)

# === Fixtures ===

HEAD = 'a' * 40


def stopped_state() -> DispatchState:
    """Build reconciled empty execution."""
    return DispatchState(
        1,
        None,
        HEAD,
        True,
        False,
        False,
        (),
        (
            DispatchClaim(
                'first',
                HEAD,
                'initial',
                1,
                'completed',
                True,
                'no_progress',
                True,
                HEAD,
            ),
        ),
        recovery_run=1,
    )


# === Admission ===


@pytest.mark.parametrize(
    ('evidence', 'outcome'),
    [
        (WorkEvidence(HEAD, HEAD, True, False), 'no_progress'),
        (WorkEvidence(HEAD, HEAD, False, False), 'local_changes'),
        (WorkEvidence(HEAD, HEAD, True, True), 'local_changes'),
        (WorkEvidence(HEAD, 'b' * 40, True, False), 'local_changes'),
        (WorkEvidence(HEAD, 'b' * 40, True, False, 'b' * 40), 'remote_commit'),
        (WorkEvidence(HEAD, 'b' * 40, True, False, 'b' * 40, 'b' * 40), 'delivered'),
        (
            WorkEvidence(HEAD, 'b' * 40, True, False, 'c' * 40, 'b' * 40),
            'local_changes',
        ),
        (
            WorkEvidence(HEAD, 'b' * 40, True, False, 'b' * 40, 'c' * 40),
            'remote_commit',
        ),
    ],
    ids=[
        'empty',
        'dirty',
        'other-ref',
        'local-commit',
        'remote-only',
        'pr',
        'stale-remote',
        'stale-pr',
    ],
)
def test_outcome_separates_absence_preservation_and_delivery(
    evidence: WorkEvidence, outcome: str
) -> None:
    assert work_outcome(evidence) == outcome


def test_reconciled_empty_execution_allows_one_explicit_recovery() -> None:
    decision = dispatch_decision(stopped_state(), 'resume')

    assert decision.allowed is True
    assert decision.reason == 'RECOVERY'
    assert decision.return_number == 0


def test_recovery_budget_survives_another_session() -> None:
    state = stopped_state()
    state = replace(
        state,
        recovery_run=2,
        claims=(
            *state.claims,
            DispatchClaim(
                'resume', HEAD, 'recovery', 2, 'completed', True, 'no_progress', True
            ),
        ),
    )

    assert dispatch_decision(state, 'another').reason == 'RECOVERY_EXHAUSTED'


def test_known_empty_execution_still_requires_reconciliation() -> None:
    state = stopped_state()
    state = replace(state, claims=(replace(state.claims[0], reconciled=False),))

    assert dispatch_decision(state, 'resume').reason == 'RECONCILE_REQUIRED'


@pytest.mark.parametrize('outcome', ['local_changes', 'remote_commit', 'delivered'])
def test_recovery_does_not_regenerate_existing_work(outcome: str) -> None:
    state = stopped_state()
    state = replace(state, claims=(replace(state.claims[0], outcome=outcome),))

    assert dispatch_decision(state, 'resume').reason == 'RECOVERY_NOT_ELIGIBLE'


def test_recovery_cannot_target_an_older_attempt() -> None:
    state = stopped_state()
    state = replace(
        state,
        claims=(
            *state.claims,
            DispatchClaim(
                'next',
                HEAD,
                'correction',
                3,
                'completed',
                True,
                'no_progress',
                True,
                HEAD,
            ),
        ),
    )

    assert dispatch_decision(state, 'resume').reason == 'RECOVERY_NOT_ELIGIBLE'


def test_recovery_does_not_bypass_the_third_review() -> None:
    state = replace(stopped_state(), reviews=('a' * 40, 'b' * 40, 'c' * 40))

    assert dispatch_decision(state, 'resume').reason == 'LEAD_COMPLETION'


def test_plain_trigger_does_not_repeat_a_reconciled_initial_execution() -> None:
    state = replace(stopped_state(), recovery_run=None)

    assert dispatch_decision(state, 'another').reason == 'INITIAL_ALREADY_RESERVED'


def test_unreconciled_no_progress_blocks_lead_writing() -> None:
    state = stopped_state()
    state = replace(state, claims=(replace(state.claims[0], reconciled=False),))
    proof = ReleaseProof('handoff', 'handoff', HEAD, HEAD, True, True, True)

    assert lead_write_allowed(state, proof) is False


def test_recovery_does_not_follow_a_changed_target_head() -> None:
    state = replace(stopped_state(), head='b' * 40)

    assert dispatch_decision(state, 'resume').reason == 'RECOVERY_NOT_ELIGIBLE'
