"""Live evaluation command."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from reply_assistant.evaluation import EvaluationReport, evaluate
from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.model_client import (
    ClosableModelClient,
    FallbackClient,
    OpenAICompatibleClient,
)
from reply_assistant.settings import Settings

# === Reports ===

CAVEAT = (
    'Manual fact review is required; passing checks do not prove factual grounding.'
)
VERDICTS = {True: 'passed', False: 'failed'}


def _client(settings: Settings) -> ClosableModelClient:
    """Build the configured client."""
    if settings.fallback_provider_api_key is None:
        return OpenAICompatibleClient.from_settings(settings)
    return FallbackClient.from_settings(settings)


def _markdown(report: EvaluationReport) -> str:
    """Render the Markdown summary."""
    lines = ['# Live evaluation', '']
    lines.extend(f'- {case.id}: {VERDICTS[case.passed]}' for case in report.cases)
    return '\n'.join([*lines, '', CAVEAT]) + '\n'


def _write_reports(output_dir: Path, report: EvaluationReport) -> None:
    """Write both report files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode='json'), ensure_ascii=False)
    (output_dir / 'results.json').write_text(payload, encoding='utf-8')
    (output_dir / 'summary.md').write_text(_markdown(report), encoding='utf-8')


# === Command ===


async def run(output_dir: Path) -> int:
    """Run the live evaluation."""
    try:
        settings = Settings()
        kb = await load_knowledge_base(settings.kb_path)
        model = _client(settings)
        try:
            report = await evaluate(kb, model)
        finally:
            await model.aclose()
        await asyncio.to_thread(_write_reports, output_dir, report)
    except Exception:
        print('Live evaluation failed.')
        return 1
    if report.passed:
        print('Live evaluation passed.')
        return 0
    print('Live evaluation failed.')
    return 1


def main() -> None:
    """Run the command."""
    parser = argparse.ArgumentParser(
        description='Evaluate the three public demonstration cases.'
    )
    parser.add_argument('--output-dir', type=Path, required=True)
    sys.exit(asyncio.run(run(parser.parse_args().output_dir)))


if __name__ == '__main__':
    main()
