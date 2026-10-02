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


def package_copy(
    directory: Path,
    only_correct: bool = False,
    mutate_answer: bool = False,
    balanced: bool = False,
) -> Path:
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
    if only_correct or mutate_answer or balanced:
        import json

        corpus_path = destination / 'development.json'
        corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
        if only_correct:
            corpus['cases'] = [
                case
                for case in corpus['cases']
                if case['label']['proposed_verdict'] == 'correct'
                and case['label']['verdict'] == 'correct'
            ]
        if mutate_answer:
            for case in corpus['cases']:
                answer = case['observation']['answer']
                answer['customer_reply'] = 'Zeolite Powder costs 99.00 USD.'
                answer['kb_match'] = 'found'
        if balanced:
            correct = [
                case
                for case in corpus['cases']
                if case['label']['proposed_verdict'] == 'correct'
            ]
            incorrect = [
                case
                for case in corpus['cases']
                if case['label']['proposed_verdict'] == 'incorrect'
            ]
            en = [case for case in correct + incorrect if '-en-' in case['case_id']]
            ru = [case for case in correct + incorrect if '-ru-' in case['case_id']]
            corpus['cases'] = en[:10] + ru[:10]
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
def test_acceptance_ready_package_exits_zero(tmp_path: Path) -> None:
    package = package_copy(tmp_path, balanced=True)
    out = tmp_path / 'out'
    code, _, stderr = run_cli(
        'acceptance', '--package', str(package), '--out', str(out)
    )

    assert code == 0, (stderr,)
    assert (out / 'report.json').is_file()
    assert (out / 'report.md').is_file()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_acceptance_failed_threshold_exits_one(tmp_path: Path) -> None:
    package = package_copy(tmp_path, balanced=True)
    corpus_path = package
    import json as json_module

    corpus = json_module.loads(corpus_path.read_text(encoding='utf-8'))
    first = corpus['cases'][0]
    first['observation']['answer']['customer_reply'] = 'Zeolite Powder costs 99.00 USD.'
    first['observation']['answer']['kb_match'] = 'found'
    corpus_path.write_text(
        json_module.dumps(corpus, ensure_ascii=False), encoding='utf-8'
    )
    out = tmp_path / 'out'
    code, _, stderr = run_cli(
        'acceptance', '--package', str(package), '--out', str(out)
    )

    assert code == 1, (stderr,)
    assert (out / 'report.json').is_file()


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_write_failure_is_safe(tmp_path: Path) -> None:
    parent = tmp_path / 'locked'
    parent.mkdir()
    inner = package_copy(parent)
    parent.chmod(0o555)

    try:
        code, _, stderr = run_cli(
            'replay', '--package', str(inner), '--out', str(parent / 'out')
        )
    finally:
        parent.chmod(0o755)

    assert code == 2
    assert 'Traceback' not in stderr
    assert not (parent / 'out').exists()


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
    package = package_copy(tmp_path, only_correct=True)
    out = tmp_path / 'out'
    before = {
        path.name: digest(path)
        for path in sorted(package.parent.rglob('*'))
        if path.is_file()
    }

    code, _, _ = run_cli('replay', '--package', str(package), '--out', str(out))
    assert code == 0

    run_cli('replay', '--package', str(package), '--out', str(out))

    after = {
        path.name: digest(path)
        for path in sorted(package.parent.rglob('*'))
        if path.is_file()
    }
    assert before == after


@pytest.mark.xfail(strict=True, reason='E12 not implemented')
def test_runs_without_provider_key_or_network(tmp_path: Path) -> None:
    package = package_copy(tmp_path, only_correct=True)
    out = tmp_path / 'out'

    code, stdout, stderr = run_cli(
        'replay', '--package', str(package), '--out', str(out)
    )

    assert code == 0
    assert stdout == ''
    assert 'Traceback' not in stderr
