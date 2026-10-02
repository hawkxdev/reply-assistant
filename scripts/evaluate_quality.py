"""Offline quality evaluation command."""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from reply_assistant.knowledge_base import KnowledgeBase
from reply_assistant.quality_corpus import (
    LoadedQualityPackage,
    QualityInputError,
    VerifiedCase,
    load_quality_package,
)
from reply_assistant.quality_facts import VerifiedFactIndex, build_fact_index
from reply_assistant.quality_report import (
    CaseEntry,
    CaseOutcome,
    ClaimEntry,
    QualityReport,
    Readiness,
    ReportMeta,
    acceptance_gate,
    build_report,
    gate_value,
    render_json,
    render_markdown,
)
from reply_assistant.quality_rules import (
    FieldAssessment,
    PolicyLanguage,
    SourcePolicy,
    Stage,
    assess_answer,
    assess_field,
)

# === Command grammar ===

MODES = ('replay', 'acceptance')
DOCUMENTS = ('sources.json', 'facts.json', 'questions.json')
JSON_NAME = 'report.json'
MARKDOWN_NAME = 'report.md'


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog='evaluate_quality',
        description='Evaluate one verified quality package offline.',
    )
    parser.add_argument('mode', choices=MODES, help='replay or acceptance')
    parser.add_argument('--package', type=Path, required=True, help='corpus file')
    parser.add_argument(
        '--out', type=Path, required=True, help='new directory of the reports'
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the offline evaluation."""
    try:
        arguments = _arguments(argv)
    except SystemExit as error:
        return int(error.code or 0)
    mode = str(arguments.mode)
    package = Path(arguments.package)
    out_dir = Path(arguments.out)
    return asyncio.run(_run(mode, package, out_dir))


async def _run(mode: str, package: Path, out_dir: Path) -> int:
    """Execute one evaluation run."""
    # Step 1: verify the package documents and the destination off the loop.
    problem = await asyncio.to_thread(_problem, package, out_dir)
    if problem is not None:
        print(problem, file=sys.stderr)
        return 2
    documents = [package.parent / name for name in DOCUMENTS]
    # Step 2: load the verified package.
    try:
        loaded = await load_quality_package(
            package.parent, documents[0], documents[1], documents[2], [package]
        )
    except QualityInputError as error:
        print(f'invalid package: {error}', file=sys.stderr)
        return 2
    # Step 3: assess both fields of every recorded case.
    entries = _assess(loaded)
    readiness = acceptance_gate(_outcomes(entries))
    report = _report(loaded, entries, readiness)
    # Step 4: publish the pair only after both renders succeed.
    try:
        await asyncio.to_thread(_publish, out_dir, report)
    except FileExistsError:
        print('output directory already exists', file=sys.stderr)
        return 2
    except Exception:
        print('report publication failed', file=sys.stderr)
        return 2
    # Step 5: derive the exit code of the mode.
    return _exit_code(mode, entries, readiness)


# === Destinations ===


def _problem(package: Path, out_dir: Path) -> str | None:
    """Report one input problem."""
    documents = [package.parent / name for name in DOCUMENTS]
    for document in (package, *documents):
        if not document.is_file():
            return f'package file is missing: {document.name}'
    if _overlaps(out_dir, package):
        return 'output directory overlaps the package location'
    if out_dir.exists():
        return 'output directory already exists'
    return None


def _overlaps(out_dir: Path, package: Path) -> bool:
    """Report one unsafe destination."""
    destination = out_dir.resolve()
    location = package.resolve()
    folder = location.parent
    if destination in (location, folder):
        return True
    return destination in folder.parents or folder in destination.parents


# === Assessment ===


def _assess(package: LoadedQualityPackage) -> tuple[CaseEntry, ...]:
    """Assess every package case."""
    paths = {source.id: source.path for source in package.sources.sources}
    indexes: dict[str, VerifiedFactIndex] = {}
    return tuple(_assess_case(item, indexes, paths) for item in package.cases)


def _assess_case(
    verified: VerifiedCase,
    indexes: dict[str, VerifiedFactIndex],
    paths: Mapping[str, str],
) -> CaseEntry:
    """Assess one recorded case."""
    case = verified.case
    question = verified.assessment.question
    observation = verified.assessment.observation
    if observation.outcome != 'answer' or observation.answer is None:
        return CaseEntry(
            case_id=case.id,
            language=question.language,
            source_path=paths[question.source_id],
            question=question.message,
            answer='',
            execution_status='recorded_failure',
            factual_verdict=None,
            human_status=case.label.status,
            human_verdict=case.label.verdict,
            grounds=(),
            unresolved=(),
            claims=(),
            categories=tuple(case.categories),
        )
    try:
        answer = observation.answer
        index = _index_for(indexes, verified)
        policy = _policy(
            verified.assessment.catalogue, observation.stage, question.language
        )
        customer = assess_field(
            answer.customer_reply,
            index,
            'customer_reply',
            answer.upsell_product_id,
            policy,
        )
        hint = assess_field(
            answer.upsell_hint,
            index,
            'upsell_hint',
            answer.upsell_product_id,
            policy,
        )
        result = assess_answer(customer, hint, question, answer, index, policy)
    except Exception:
        print(f'case {case.id} could not be evaluated', file=sys.stderr)
        return CaseEntry(
            case_id=case.id,
            language=question.language,
            source_path=paths[question.source_id],
            question=question.message,
            answer='',
            execution_status='evaluator_error',
            factual_verdict=None,
            human_status=case.label.status,
            human_verdict=case.label.verdict,
            grounds=(),
            unresolved=(),
            claims=(),
            categories=tuple(case.categories),
        )
    return CaseEntry(
        case_id=case.id,
        language=question.language,
        source_path=paths[question.source_id],
        question=question.message,
        answer=answer.customer_reply,
        execution_status='evaluated',
        factual_verdict=result.verdict,
        human_status=case.label.status,
        human_verdict=case.label.verdict,
        grounds=result.grounds,
        unresolved=result.unresolved,
        claims=(*_claims(customer), *_claims(hint)),
        categories=tuple(case.categories),
    )


def _index_for(
    indexes: dict[str, VerifiedFactIndex], verified: VerifiedCase
) -> VerifiedFactIndex:
    """Build one cached index."""
    source_id = verified.assessment.question.source_id
    index = indexes.get(source_id)
    if index is None:
        index = build_fact_index(
            verified.assessment.catalogue, verified.assessment.product_facts
        )
        indexes[source_id] = index
    return index


def _policy(
    catalogue: KnowledgeBase, stage: Stage | None, language: PolicyLanguage
) -> SourcePolicy:
    """Build the source policy."""
    return SourcePolicy(
        disclaimer=catalogue.disclaimer,
        stage=stage,
        language=language,
        forbidden_stems=tuple(catalogue.forbidden_claims),
    )


def _claims(assessment: FieldAssessment) -> tuple[ClaimEntry, ...]:
    """Collect one field claims."""
    return tuple(
        ClaimEntry(
            kind=claim.kind,
            expected=claim.expected,
            found=claim.found,
            start=claim.start,
            end=claim.end,
            ground=claim.product_id,
        )
        for claim in (*assessment.claims, *assessment.service_fragments)
    )


# === Report ===


def _outcomes(entries: Sequence[CaseEntry]) -> list[CaseOutcome]:
    """Map entries to outcomes."""
    # Step 1: the package records no contamination, so every case counts independent.
    return [
        CaseOutcome(
            execution_status=entry.execution_status,
            factual_verdict=entry.factual_verdict,
            human_status=entry.human_status,
            human_verdict=entry.human_verdict,
            language=entry.language,
            independent=True,
        )
        for entry in entries
    ]


def _report(
    package: LoadedQualityPackage,
    entries: Sequence[CaseEntry],
    readiness: Readiness,
) -> QualityReport:
    """Assemble one quality report."""
    meta = ReportMeta(
        rules_id=package.sources.rules_id,
        rules_sha256=package.sources.rules_sha256,
        sources=[(source.path, source.sha256) for source in package.sources.sources],
    )
    return build_report(meta, entries, evaluator_gate=gate_value(readiness.state))


# === Publication ===


def _publish(out_dir: Path, report: QualityReport) -> None:
    """Write the report pair."""
    payload = render_json(report)
    page = render_markdown(report)
    out_dir.mkdir(parents=True)
    pending = (out_dir / f'{JSON_NAME}.part', out_dir / f'{MARKDOWN_NAME}.part')
    published = (out_dir / JSON_NAME, out_dir / MARKDOWN_NAME)
    try:
        pending[0].write_text(payload, encoding='utf-8')
        pending[1].write_text(page, encoding='utf-8')
        _replace(pending[0], published[0])
        _replace(pending[1], published[1])
    except OSError:
        for path in (*pending, *published):
            path.unlink(missing_ok=True)
        out_dir.rmdir()
        raise


def _replace(pending: Path, published: Path) -> None:
    """Publish one report file."""
    os.replace(pending, published)


# === Exit codes ===


def _exit_code(mode: str, entries: Sequence[CaseEntry], readiness: Readiness) -> int:
    """Derive the mode exit code."""
    if mode == 'acceptance':
        reasons = '; '.join(readiness.reasons)
        if readiness.state == 'not_ready':
            print(f'acceptance not ready: {reasons}', file=sys.stderr)
            return 2
        if readiness.state == 'fail_':
            print(f'acceptance failed: {reasons}', file=sys.stderr)
            return 1
        return 0
    failures = sum(1 for entry in entries if entry.execution_status != 'evaluated')
    if failures:
        print(f'replay incomplete: {failures} execution failures', file=sys.stderr)
        return 2
    findings = sum(1 for entry in entries if entry.factual_verdict != 'confirmed')
    if findings:
        print(f'replay found content findings in {findings} cases', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
