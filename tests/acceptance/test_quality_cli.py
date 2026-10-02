"""Acceptance for issue 87."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

# === Data ===

ROOT = Path(__file__).parents[2]
DATA = ROOT / 'evals' / 'quality' / 'v1'
SCRIPT = ROOT / 'scripts' / 'evaluate_quality.py'


# === Fixtures and helpers ===


def run_cli(*args: str) -> tuple[int, str, str]:
    """Run the offline command as a real subprocess."""
    environment = {
        'PATH': '/usr/bin:/bin:/usr/local/bin',
        'HOME': str(ROOT / '..'),
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=environment,
    )
    return result.returncode, result.stdout, result.stderr


def package_copy(directory: Path, only_correct: bool = False) -> Path:
    """Copy the public package inputs into one directory."""
    destination = directory / 'package'
    destination.mkdir(parents=True, exist_ok=True)
    for name in (
        'sources.json',
        'facts.json',
        'questions.json',
        'development.json',
    ):
        raw = (DATA / name).read_bytes()
        (destination / name).write_bytes(raw)
    if only_correct:
        import json

        corpus_path = destination / 'development.json'
        corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
        corpus['cases'] = [
            case
            for case in corpus['cases']
            if case['label']['proposed_verdict'] == 'correct'
            and case['label']['verdict'] == 'correct'
        ]
        corpus_path.write_bytes(
            json.dumps(corpus, ensure_ascii=False, indent=2).encode('utf-8')
        )
    kb = destination / 'kb'
    kb.mkdir(exist_ok=True)
    for name in ('example-en.yaml', 'example-ru.yaml'):
        (kb / name).write_bytes((ROOT / 'kb' / name).read_bytes())
    return destination / 'development.json'


def digest(path: Path) -> str:
    """Hash one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# === Replay ===


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_replay_clean_package_exits_zero_and_writes_pair(
    tmp_path: Path,
) -> None:
    package = package_copy(tmp_path, only_correct=True)
    out = tmp_path / 'out'
    code, _, stderr = run_cli('replay', '--package', str(package), '--out', str(out))

    assert code == 0, (stderr,)
    assert (out / 'report.json').is_file()
    assert (out / 'report.md').is_file()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_replay_with_findings_exits_one(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'
    code, _, _ = run_cli('replay', '--package', str(package), '--out', str(out))

    assert code == 1
    body = (out / 'report.md').read_text(encoding='utf-8')
    assert 'error' in body


# === Modes and failures ===


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_acceptance_on_forty_cases_is_not_ready(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'
    code, _, stderr = run_cli(
        'acceptance', '--package', str(package), '--out', str(out)
    )

    assert code == 2, stderr
    assert 'not ready' in stderr.lower()
    assert (out / 'report.json').is_file()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_missing_package_exits_two_without_reports(tmp_path: Path) -> None:
    out = tmp_path / 'out'
    code, _, stderr = run_cli(
        'replay', '--package', str(tmp_path / 'absent.json'), '--out', str(out)
    )

    assert code == 2
    assert 'package file is missing' in stderr
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_existing_out_directory_is_refused(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'
    out.mkdir()
    sentinel = out / 'sentinel.txt'
    sentinel.write_text('keep me')

    code, _, stderr = run_cli('replay', '--package', str(package), '--out', str(out))

    assert code == 2
    assert 'output directory already exists' in stderr
    assert sentinel.read_text() == 'keep me'
    assert not (out / 'report.json').exists()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_invalid_package_exits_two(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    target = package
    target.write_text('{ not json')
    out = tmp_path / 'out'

    code, _, stderr = run_cli('replay', '--package', str(target), '--out', str(out))

    assert code == 2
    assert 'invalid package' in stderr
    assert not (out / 'report.json').exists()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_unknown_mode_exits_two(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'

    code, _, stderr = run_cli('blast', '--package', str(package), '--out', str(out))

    assert code == 2
    assert 'invalid choice' in stderr


# === Safety ===


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_package_bytes_unchanged_after_run(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'
    code, _, _ = run_cli('replay', '--package', str(package), '--out', str(out))
    assert code == 0
    before = {
        path.name: digest(path)
        for path in sorted(package.parent.rglob('*'))
        if path.is_file()
    }

    run_cli('replay', '--package', str(package), '--out', str(out))

    after = {
        path.name: digest(path)
        for path in sorted(package.parent.rglob('*'))
        if path.is_file()
    }
    assert before == after


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_runs_without_provider_key_or_network(tmp_path: Path) -> None:
    package = package_copy(tmp_path)
    out = tmp_path / 'out'

    code, stdout, stderr = run_cli(
        'replay', '--package', str(package), '--out', str(out)
    )

    assert code == 1
    assert stdout == ''
    assert 'Traceback' not in stderr
