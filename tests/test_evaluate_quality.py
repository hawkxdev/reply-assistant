"""Offline command unit tests."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# === Data ===

ROOT = Path(__file__).parents[1]
DATA = ROOT / 'evals' / 'quality' / 'v1'

# === Helpers ===


def cli_module() -> ModuleType:
    """Load the offline command."""
    spec = importlib.util.spec_from_file_location(
        'quality_cli_unit', ROOT / 'scripts/evaluate_quality.py'
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_package(
    folder: Path, *, only_correct: bool = False, failure: bool = False
) -> Path:
    """Write one verified package."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('sources.json', 'facts.json', 'questions.json'):
        (folder / name).write_bytes((DATA / name).read_bytes())
    corpus = json.loads((DATA / 'development.json').read_text(encoding='utf-8'))
    if only_correct:
        corpus['cases'] = [
            case
            for case in corpus['cases']
            if case['label']['proposed_verdict'] == 'correct'
            and case['label']['verdict'] == 'correct'
        ]
    if failure:
        first: dict[str, Any] = corpus['cases'][0]
        first['observation'] = {
            'outcome': 'provider_error',
            'stage': None,
            'answer': None,
            'error_code': 'timeout',
        }
        first['answer_origin'] = {
            'kind': 'recorded',
            'reference': 'runs/r1.json',
            'sha256': '0' * 64,
            'parent_case_id': None,
            'record_pointer': '',
            'generation': {
                'provider': None,
                'model': None,
                'max_output_tokens': 1,
                'temperature': None,
                'input_tokens': 0,
                'output_tokens': 0,
                'attempts': 1,
                'run_reference': None,
            },
        }
    (folder / 'development.json').write_text(
        json.dumps(corpus, ensure_ascii=False), encoding='utf-8'
    )
    kb = folder / 'kb'
    kb.mkdir(exist_ok=True)
    for name in ('example-en.yaml', 'example-ru.yaml'):
        (kb / name).write_bytes((ROOT / 'kb' / name).read_bytes())
    return folder / 'development.json'


# === Tests ===


def test_real_package_replay_reads_kb_from_repository_root(
    tmp_path: Path,
) -> None:
    cli = cli_module()
    out = tmp_path / 'out'

    code = cli.main(
        ['replay', '--package', str(DATA / 'development.json'), '--out', str(out)]
    )

    assert code == 1
    assert (out / 'report.json').is_file()
    assert (out / 'report.md').is_file()


def test_recorded_failure_exits_two_with_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    package = build_package(tmp_path / 'package', failure=True)
    out = tmp_path / 'out'

    code = cli.main(['replay', '--package', str(package), '--out', str(out)])

    assert code == 2
    assert (out / 'report.json').is_file()
    assert 'replay incomplete' in capsys.readouterr().err


def test_out_on_package_location_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    package = build_package(tmp_path / 'package')

    for unsafe in (package.parent, package.parent.parent):
        code = cli.main(['replay', '--package', str(package), '--out', str(unsafe)])
        assert code == 2
        assert 'overlaps' in capsys.readouterr().err

    assert not (package.parent / 'report.json').exists()


def test_failed_second_publication_leaves_no_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    package = build_package(tmp_path / 'package', only_correct=True)
    out = tmp_path / 'out'
    published: list[str] = []
    original = cli._replace

    def failing(source: Path, target: Path) -> None:
        """Publish all but the second file."""
        published.append(target.name)
        if len(published) == 2:
            raise OSError('disk full')
        original(source, target)

    monkeypatch.setattr(cli, '_replace', failing)

    code = cli.main(['replay', '--package', str(package), '--out', str(out)])

    assert code == 2
    assert published == ['report.json', 'report.md']
    assert not (out / 'report.json').exists()
    assert not (out / 'report.md').exists()
    assert not out.exists()
    assert 'publication failed' in capsys.readouterr().err


def test_render_failure_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    package = build_package(tmp_path / 'package', only_correct=True)
    out = tmp_path / 'out'

    def broken(report: object) -> str:
        """Fail the Markdown render."""
        raise RuntimeError('renderer exploded')

    monkeypatch.setattr(cli, 'render_markdown', broken)

    code = cli.main(['replay', '--package', str(package), '--out', str(out)])

    assert code == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert 'publication failed' in err
    assert 'Traceback' not in err


def test_usage_errors_return_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = cli_module()
    package = build_package(tmp_path / 'package')

    assert cli.main(['replay', '--package', str(package)]) == 2
    assert (
        cli.main(
            ['replay', '--package', str(package), '--out', str(tmp_path / 'o'), '--wat']
        )
        == 2
    )
    assert 'unrecognized arguments' in capsys.readouterr().err
