"""Live command unit tests."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from reply_assistant.evaluation import EvaluationCaseResult, EvaluationReport

ROOT = Path(__file__).parents[1]


def cli_module() -> ModuleType:
    """Load the live command."""
    spec = importlib.util.spec_from_file_location(
        'live_cli_unit', ROOT / 'scripts/evaluate_live.py'
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_exits_with_the_returned_success_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = cli_module()

    async def run(output_dir: Path) -> int:
        """Succeed without calls."""
        return 0

    monkeypatch.setattr(cli, 'run', run)
    monkeypatch.setattr('sys.argv', ['evaluate_live.py', '--output-dir', str(tmp_path)])

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 0


def test_documented_command_fails_closed_without_a_key(tmp_path: Path) -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith('REPLY_ASSISTANT_')
    }

    command = [
        sys.executable,
        str(ROOT / 'scripts/evaluate_live.py'),
        '--output-dir',
        str(tmp_path),
    ]

    completed = subprocess.run(  # noqa: S603
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 1
    assert completed.stdout == 'Live evaluation failed.\n'
    assert completed.stderr == ''


def test_markdown_states_the_verdict_of_each_case() -> None:
    cli = cli_module()
    report = EvaluationReport(
        passed=False,
        cases=[
            EvaluationCaseResult(
                id='price',
                message='price message',
                passed=True,
                failures=[],
                suggestion=None,
                error=None,
            ),
            EvaluationCaseResult(
                id='delivery',
                message='delivery message',
                passed=False,
                failures=['kb_match'],
                suggestion=None,
                error='provider_error',
            ),
        ],
    )

    summary = cli._markdown(report)

    assert '- price: passed' in summary
    assert '- delivery: failed' in summary
