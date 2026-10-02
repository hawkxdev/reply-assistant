"""Quality metrics and readiness."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
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
AnswerSetStatus = Literal['all_confirmed', 'has_errors', 'needs_review', 'incomplete']
EvaluatorGate = Literal['pass', 'fail', 'not_ready']
GroupAxis = Literal['language', 'category']

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
    independent: bool = False


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
    missing_verdict = sum(
        1 for item in outcomes if _is_evaluated(item) and item.factual_verdict is None
    )
    if missing_verdict:
        reasons.append(f'{missing_verdict} evaluated outcomes carry no factual verdict')
    stray_verdict = sum(
        1
        for item in outcomes
        if not _is_evaluated(item) and item.factual_verdict is not None
    )
    if stray_verdict:
        reasons.append(
            f'{stray_verdict} outcomes were not evaluated but carry a verdict'
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


# === Report records ===

REPORT_KIND = 'quality-evaluation'
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReportMeta:
    """Identity of the inputs."""

    rules_id: str
    rules_sha256: str
    sources: Sequence[tuple[str, str]]


@dataclass(frozen=True)
class ClaimEntry:
    """One checked claim."""

    kind: str
    expected: str
    found: str
    start: int
    end: int
    ground: str


@dataclass(frozen=True)
class CaseEntry:
    """One case of the report."""

    case_id: str
    language: Language
    source_path: str
    question: str
    answer: str
    execution_status: ExecutionStatus
    factual_verdict: FactualVerdict | None
    human_status: HumanStatus
    human_verdict: HumanVerdict | None
    grounds: Sequence[str]
    unresolved: Sequence[str]
    claims: Sequence[ClaimEntry] = ()
    categories: Sequence[str] = ()


@dataclass(frozen=True)
class GroupSummary:
    """Metrics of one group."""

    axis: GroupAxis
    name: str
    case_ids: tuple[str, ...]
    metrics: Metrics


@dataclass(frozen=True)
class QualityReport:
    """Assembled quality report."""

    report_kind: str
    schema_version: int
    meta: ReportMeta
    summary: Metrics
    cases: tuple[CaseEntry, ...]
    answer_set_status: AnswerSetStatus
    evaluator_gate: EvaluatorGate
    groups: tuple[GroupSummary, ...]


# === Report assembly ===


def _answer_set_status(entries: Sequence[CaseEntry]) -> AnswerSetStatus:
    """Answer set status."""

    if not entries:
        return 'incomplete'
    if any(
        entry.execution_status != 'evaluated' or entry.factual_verdict is None
        for entry in entries
    ):
        return 'incomplete'
    verdicts = {entry.factual_verdict for entry in entries}
    if 'error' in verdicts:
        return 'has_errors'
    if 'manual_review' in verdicts:
        return 'needs_review'
    return 'all_confirmed'


def gate_value(state: GateState) -> EvaluatorGate:
    """Published gate value."""

    if state == 'pass_':
        return 'pass'
    if state == 'fail_':
        return 'fail'
    return 'not_ready'


def _report_groups(
    pairs: Sequence[tuple[CaseEntry, CaseOutcome]],
) -> tuple[GroupSummary, ...]:
    """Group summaries of entries."""

    def group(
        axis: GroupAxis,
        name: str,
        members: Sequence[tuple[CaseEntry, CaseOutcome]],
    ) -> GroupSummary:
        """Metrics of member cases."""

        return GroupSummary(
            axis=axis,
            name=name,
            case_ids=tuple(entry.case_id for entry, _ in members),
            metrics=compute_metrics([outcome for _, outcome in members]),
        )

    languages = sorted({entry.language for entry, _ in pairs})
    categories = sorted(
        {category for entry, _ in pairs for category in entry.categories}
    )
    language_groups = [
        group(
            'language',
            language,
            [pair for pair in pairs if pair[0].language == language],
        )
        for language in languages
    ]
    category_groups = [
        group(
            'category',
            category,
            [pair for pair in pairs if category in pair[0].categories],
        )
        for category in categories
    ]
    return tuple(language_groups + category_groups)


def build_report(
    meta: ReportMeta,
    entries: Sequence[CaseEntry],
    *,
    answer_set_status: AnswerSetStatus | None = None,
    evaluator_gate: EvaluatorGate | None = None,
) -> QualityReport:
    """Assemble one quality report."""

    pairs = [
        (
            entry,
            CaseOutcome(
                execution_status=entry.execution_status,
                factual_verdict=entry.factual_verdict,
                human_status=entry.human_status,
                human_verdict=entry.human_verdict,
                language=entry.language,
            ),
        )
        for entry in entries
    ]
    outcomes = [outcome for _, outcome in pairs]
    status = (
        answer_set_status
        if answer_set_status is not None
        else _answer_set_status(entries)
    )
    gate = (
        evaluator_gate
        if evaluator_gate is not None
        else gate_value(acceptance_gate(outcomes).state)
    )
    return QualityReport(
        report_kind=REPORT_KIND,
        schema_version=SCHEMA_VERSION,
        meta=meta,
        summary=compute_metrics(outcomes),
        cases=tuple(entries),
        answer_set_status=status,
        evaluator_gate=gate,
        groups=_report_groups(pairs),
    )


# === Report rendering ===


def _text(value: object) -> str:
    """Text of one optional value."""

    return 'null' if value is None else str(value)


def _pinned_path(path: str, meta: ReportMeta) -> str | None:
    """Pinned form of a path."""

    if not path.startswith('/'):
        return path
    for pinned, _digest in meta.sources:
        if not pinned.startswith('/') and path.endswith(f'/{pinned}'):
            return pinned
    return None


def _claim_payload(claim: ClaimEntry) -> dict[str, object]:
    """JSON payload of one claim."""

    return {
        'kind': claim.kind,
        'expected': claim.expected,
        'found': claim.found,
        'start': claim.start,
        'end': claim.end,
        'ground': claim.ground,
    }


def _case_payload(entry: CaseEntry, meta: ReportMeta) -> dict[str, object]:
    """JSON payload of one case."""

    return {
        'case_id': entry.case_id,
        'language': entry.language,
        'categories': list(entry.categories),
        'source_path': _pinned_path(entry.source_path, meta),
        'question': entry.question,
        'answer': entry.answer,
        'execution_status': entry.execution_status,
        'factual_verdict': entry.factual_verdict,
        'human_status': entry.human_status,
        'human_verdict': entry.human_verdict,
        'grounds': list(entry.grounds),
        'unresolved': list(entry.unresolved),
        'claims': [_claim_payload(claim) for claim in entry.claims],
    }


def _group_payload(group: GroupSummary) -> dict[str, object]:
    """JSON payload of one group."""

    return {
        'axis': group.axis,
        'name': group.name,
        'case_ids': list(group.case_ids),
        'metrics': asdict(group.metrics),
    }


def render_json(report: QualityReport) -> str:
    """Render the report as JSON."""

    payload: dict[str, object] = {
        'report_kind': report.report_kind,
        'schema_version': report.schema_version,
        'rules_id': report.meta.rules_id,
        'rules_sha256': report.meta.rules_sha256,
        'sources': [[path, digest] for path, digest in report.meta.sources],
        'answer_set_status': report.answer_set_status,
        'evaluator_gate': report.evaluator_gate,
        'summary': asdict(report.summary),
        'groups': [_group_payload(group) for group in report.groups],
        'cases': [_case_payload(entry, report.meta) for entry in report.cases],
    }
    return json.dumps(payload, indent=2) + '\n'


def _summary_lines(summary: Metrics) -> list[str]:
    """Markdown summary block."""

    return [
        f'- Total: {summary.total}',
        f'- Evaluated: {summary.evaluated}',
        f'- Confirmed: {summary.confirmed}',
        f'- Error: {summary.error}',
        f'- Manual review: {summary.manual_review}',
        f'- Failures: {summary.failures}',
        f'- Pending references: {summary.pending_references}',
        f'- Disputed references: {summary.disputed_references}',
        f'- Unresolved references: {summary.unresolved_references}',
        f'- C size: {summary.c_size}',
        f'- W size: {summary.w_size}',
        f'- False confirmation rate: {_text(summary.false_confirmation_rate)}',
        f'- False rejection rate: {_text(summary.false_rejection_rate)}',
        f'- Manual share: {_text(summary.manual_share)}',
    ]


def _reason_lines(title: str, reasons: Sequence[str]) -> list[str]:
    """Markdown block of reasons."""

    lines = [f'{title}:']
    lines.extend(f'- {reason}' for reason in reasons)
    lines.append('')
    return lines


def _group_lines(title: str, groups: Sequence[GroupSummary]) -> list[str]:
    """Markdown block of groups."""

    lines = ['', f'{title}:', '']
    for group in groups:
        links = ', '.join(f'[{case_id}](#{case_id})' for case_id in group.case_ids)
        lines.append(f'- {group.name}: cases {links}')
        lines.extend(f'  {line}' for line in _summary_lines(group.metrics))
    lines.append('')
    return lines


def _claim_lines(claims: Sequence[ClaimEntry]) -> list[str]:
    """Markdown block of claims."""

    lines = ['Claims:']
    lines.extend(
        f'- {claim.kind}: span {claim.start}-{claim.end}, '
        f'expected {claim.expected}, found {claim.found}, '
        f'ground {claim.ground}'
        for claim in claims
    )
    lines.append('')
    return lines


def _case_lines(entry: CaseEntry, meta: ReportMeta) -> list[str]:
    """Markdown block of one case."""

    lines = [
        f'### {entry.case_id}',
        '',
        f'- Language: {entry.language}',
        f'- Source: {_text(_pinned_path(entry.source_path, meta))}',
        f'- Execution: {entry.execution_status}',
        f'- Verdict: {_text(entry.factual_verdict)}',
        f'- Human: {entry.human_status}/{_text(entry.human_verdict)}',
        '',
        f'Question: {entry.question}',
        '',
        f'Answer: {entry.answer}',
        '',
    ]
    lines.extend(_reason_lines('Grounds', entry.grounds))
    lines.extend(_reason_lines('Unresolved', entry.unresolved))
    lines.extend(_claim_lines(entry.claims))
    return lines


def render_markdown(report: QualityReport) -> str:
    """Render the report as Markdown."""

    language_groups = [group for group in report.groups if group.axis == 'language']
    category_groups = [group for group in report.groups if group.axis == 'category']
    lines = [
        '# Quality evaluation report',
        '',
        f'- Report kind: {report.report_kind}',
        f'- Schema version: {report.schema_version}',
        f'- Rules: {report.meta.rules_id} ({report.meta.rules_sha256})',
        '- Sources:',
    ]
    lines.extend(f'  - {path} ({digest})' for path, digest in report.meta.sources)
    lines.extend(
        [
            f'- Answer set: {report.answer_set_status}',
            f'- Evaluator gate: {report.evaluator_gate}',
        ]
    )
    lines.extend(['', '## Summary', ''])
    lines.extend(_summary_lines(report.summary))
    lines.extend(_group_lines('By language', language_groups))
    lines.extend(_group_lines('By category', category_groups))
    lines.extend(['', '## Cases', ''])
    for entry in report.cases:
        lines.extend(_case_lines(entry, report.meta))
    return '\n'.join(lines) + '\n'
