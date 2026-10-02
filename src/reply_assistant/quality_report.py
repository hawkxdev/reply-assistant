"""Quality metrics and readiness."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# === Contract types ===

ExecutionStatus = Literal[
    'evaluated', 'recorded_failure', 'invalid_input', 'evaluator_error'
]
FactualVerdict = Literal['confirmed', 'error', 'manual_review']
HumanStatus = Literal['pending', 'confirmed', 'disputed']
HumanVerdict = Literal['correct', 'incorrect', 'unresolved']
Language = Literal['en', 'ru']
GateState = Literal['pass_', 'fail_', 'not_ready']

# === Fixed bounds ===

ACCEPTANCE_SIZE = 20
BALANCE = 10
MANUAL_REVIEW_LIMIT = 4

# === Records ===


@dataclass(frozen=True)
class CaseOutcome:
    """Outcome of one case."""

    execution_status: ExecutionStatus
    factual_verdict: FactualVerdict | None
    human_status: HumanStatus
    human_verdict: HumanVerdict | None
    language: Language
    independent: bool = True


@dataclass(frozen=True)
class Metrics:
    """Summary metrics of outcomes."""

    total: int
    evaluated: int
    confirmed: int
    error: int
    manual_review: int
    failures: int
    pending_references: int
    disputed_references: int
    unresolved_references: int
    c_size: int
    w_size: int
    false_confirmation_rate: float | None
    false_rejection_rate: float | None
    manual_share: float | None


@dataclass(frozen=True)
class Readiness:
    """Acceptance readiness result."""

    state: GateState
    reasons: tuple[str, ...]


# === Shared predicates ===


def _is_evaluated(outcome: CaseOutcome) -> bool:
    """Whether execution completed."""

    return outcome.execution_status == 'evaluated'


def _carries_label(outcome: CaseOutcome, verdict: HumanVerdict) -> bool:
    """Whether label is definite."""

    return outcome.human_status == 'confirmed' and outcome.human_verdict == verdict


def _in_reference(outcome: CaseOutcome, verdict: HumanVerdict) -> bool:
    """Whether case enters reference."""

    return _is_evaluated(outcome) and _carries_label(outcome, verdict)


# === Metrics ===


def compute_metrics(outcomes: Sequence[CaseOutcome]) -> Metrics:
    """Compute exact report metrics."""

    evaluated = [item for item in outcomes if _is_evaluated(item)]
    confirmed = sum(1 for item in evaluated if item.factual_verdict == 'confirmed')
    errors = sum(1 for item in evaluated if item.factual_verdict == 'error')
    manual = sum(1 for item in evaluated if item.factual_verdict == 'manual_review')
    c_cases = [item for item in evaluated if _in_reference(item, 'correct')]
    w_cases = [item for item in evaluated if _in_reference(item, 'incorrect')]
    false_confirmations = sum(
        1 for item in w_cases if item.factual_verdict == 'confirmed'
    )
    false_rejections = sum(1 for item in c_cases if item.factual_verdict == 'error')

    return Metrics(
        total=len(outcomes),
        evaluated=len(evaluated),
        confirmed=confirmed,
        error=errors,
        manual_review=manual,
        failures=len(outcomes) - len(evaluated),
        pending_references=sum(
            1 for item in outcomes if item.human_status == 'pending'
        ),
        disputed_references=sum(
            1 for item in outcomes if item.human_status == 'disputed'
        ),
        unresolved_references=sum(
            1 for item in outcomes if item.human_verdict == 'unresolved'
        ),
        c_size=len(c_cases),
        w_size=len(w_cases),
        false_confirmation_rate=(
            false_confirmations / len(w_cases) if w_cases else None
        ),
        false_rejection_rate=(false_rejections / len(c_cases) if c_cases else None),
        manual_share=(manual / len(evaluated) if evaluated else None),
    )


# === Readiness ===


def _structural_reasons(outcomes: Sequence[CaseOutcome]) -> list[str]:
    """List structural violations."""

    reasons: list[str] = []
    if len(outcomes) != ACCEPTANCE_SIZE:
        reasons.append(f'expected {ACCEPTANCE_SIZE} outcomes, found {len(outcomes)}')
    not_evaluated = sum(1 for item in outcomes if not _is_evaluated(item))
    if not_evaluated:
        reasons.append(
            f'{not_evaluated} outcomes were not evaluated, '
            f'the measurement is incomplete'
        )
    unconfirmed = sum(
        1
        for item in outcomes
        if item.human_status != 'confirmed' or item.human_verdict is None
    )
    if unconfirmed:
        reasons.append(
            f'{unconfirmed} human references are not confirmed with a verdict'
        )
    correct = sum(1 for item in outcomes if _carries_label(item, 'correct'))
    incorrect = sum(1 for item in outcomes if _carries_label(item, 'incorrect'))
    if correct != BALANCE or incorrect != BALANCE:
        reasons.append(
            f'truth balance expected {BALANCE} correct and {BALANCE} incorrect '
            f'references, found {correct} correct and {incorrect} incorrect'
        )
    en = sum(1 for item in outcomes if item.language == 'en')
    ru = sum(1 for item in outcomes if item.language == 'ru')
    if en != BALANCE or ru != BALANCE:
        reasons.append(
            f'language balance expected {BALANCE} en and {BALANCE} ru, '
            f'found {en} en and {ru} ru'
        )
    contaminated = sum(1 for item in outcomes if not item.independent)
    if contaminated:
        reasons.append(f'{contaminated} cases are contaminated by prior access')
    return reasons


def _threshold_reasons(metrics: Metrics) -> list[str]:
    """List threshold violations."""

    reasons: list[str] = []
    if metrics.false_confirmation_rate != 0.0:
        reasons.append(
            f'false confirmation rate {metrics.false_confirmation_rate} must be zero'
        )
    if metrics.false_rejection_rate != 0.0:
        reasons.append(
            f'false rejection rate {metrics.false_rejection_rate} must be zero'
        )
    if metrics.manual_review > MANUAL_REVIEW_LIMIT:
        reasons.append(
            f'manual review {metrics.manual_review} exceeds '
            f'the limit of {MANUAL_REVIEW_LIMIT}'
        )
    return reasons


def acceptance_gate(outcomes: Sequence[CaseOutcome]) -> Readiness:
    """Assess acceptance readiness."""

    structural = _structural_reasons(outcomes)
    if structural:
        return Readiness(state='not_ready', reasons=tuple(structural))
    threshold = _threshold_reasons(compute_metrics(outcomes))
    if threshold:
        return Readiness(state='fail_', reasons=tuple(threshold))
    return Readiness(state='pass_', reasons=())
