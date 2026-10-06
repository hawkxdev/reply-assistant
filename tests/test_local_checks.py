"""Verify local gate orchestration."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def executable(name: str) -> str:
    """Resolve the fixture executable."""
    result = shutil.which(name)
    if result is None:
        raise RuntimeError(f'Missing fixture executable: {name}')
    return result


def git(root: Path, *args: str) -> str:
    """Run isolated Git commands."""
    return subprocess.check_output(  # noqa: S603
        [executable('git'), '-C', str(root), *args], text=True
    ).strip()


@pytest.fixture
def local_gate(tmp_path: Path) -> tuple[Path, Path, str, dict[str, str]]:
    """Prepare isolated gate inputs."""
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'scripts').mkdir()
    (root / 'tests').mkdir()
    (root / 'tests' / 'existing.py').write_text('existing = True\n')
    (root / 'pyproject.toml').write_text('[project]\nname = "fixture"\n')
    script = Path('scripts/check-local.sh')
    if script.is_file():
        shutil.copy2(script, root / script)
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'add', '.')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'chore: fixture base')
    base = git(root, 'rev-parse', 'HEAD')
    git(root, 'remote', 'add', 'origin', 'https://github.com/fixture/repo.git')
    tools = tmp_path / 'tools'
    tools.mkdir()
    uv = tools / 'uv'
    uv.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$*" >> "$LOCAL_UV_LOG"\n'
        'if [ "$*" = "run ruff check ." ] '
        '&& [ "${LOCAL_FAIL_RUFF:-0}" = "1" ]; then exit 23; fi\n'
        'exit 0\n'
    )
    uv.chmod(0o700)
    gh = tools / 'gh'
    gh.write_text('#!/bin/sh\ncat "$LOCAL_REVIEW_INPUT"\n')
    gh.chmod(0o700)
    env = dict(os.environ)
    env.update(PATH=f'{tools}:{env["PATH"]}', LOCAL_UV_LOG=str(tmp_path / 'uv.log'))
    return root, tmp_path / 'result', base, env


def run_gate(
    fixture: tuple[Path, Path, str, dict[str, str]],
    title: str = 'chore: local verification',
) -> subprocess.CompletedProcess[str]:
    """Execute the fixture entrypoint."""
    root, output, base, env = fixture
    return subprocess.run(  # noqa: S603
        [
            executable('bash'),
            str(root / 'scripts/check-local.sh'),
            '--base',
            base,
            '--title',
            title,
            '--output-dir',
            str(output),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_checks_record_every_required_command(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    result = run_gate(local_gate)
    _, output, base, env = local_gate

    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / 'commit.txt').read_text().strip() == base
    assert (output / 'exit-code.txt').read_text() == '0\n'
    assert Path(env['LOCAL_UV_LOG']).read_text().splitlines() == [
        'sync --locked',
        'run ruff check .',
        'run ruff format --check .',
        'run mypy .',
        'run pytest --cov',
        'run python scripts/check_conventions.py',
    ]


def test_local_checks_stop_and_preserve_a_failed_command(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    _, output, _, env = local_gate
    env['LOCAL_FAIL_RUFF'] = '1'
    result = run_gate(local_gate)

    assert result.returncode == 23
    assert (output / 'exit-code.txt').read_text() == '23\n'
    assert Path(env['LOCAL_UV_LOG']).read_text().splitlines() == [
        'sync --locked',
        'run ruff check .',
    ]


def test_local_checks_reject_a_deleted_existing_test(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    root, _, _, env = local_gate
    git(root, 'rm', 'tests/existing.py')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'chore: delete fixture')
    result = run_gate(local_gate)

    assert result.returncode != 0
    assert 'Test files deleted' in result.stderr
    assert not Path(env['LOCAL_UV_LOG']).exists()


def test_local_checks_reject_a_nonconventional_title(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    result = run_gate(local_gate, 'Move checks locally')

    assert result.returncode != 0
    assert 'Conventional Commit title required' in result.stderr


def test_local_checks_reject_uncommitted_inputs(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    root, _, _, env = local_gate
    (root / 'pyproject.toml').write_text('[project]\nname = "changed"\n')
    result = run_gate(local_gate)

    assert result.returncode != 0
    assert 'Clean working tree required' in result.stderr
    assert not Path(env['LOCAL_UV_LOG']).exists()


def change_dependencies(
    fixture: tuple[Path, Path, str, dict[str, str]], payload: str
) -> None:
    """Stage dependency review inputs."""
    root, output, _, env = fixture
    with (root / 'pyproject.toml').open('a') as stream:
        stream.write('version = "0.2.0"\n')
    git(root, 'add', 'pyproject.toml')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'chore: fixture update')
    report = output.parent / 'dependency.json'
    report.write_text(payload)
    env['LOCAL_REVIEW_INPUT'] = str(report)


def test_local_checks_reject_added_vulnerable_dependencies(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(
        local_gate,
        '[{"change_type":"added","vulnerabilities":[{"severity":"low"}]}]',
    )
    result = run_gate(local_gate)

    assert result.returncode != 0
    assert 'New vulnerable dependencies are rejected' in result.stderr


def test_local_checks_reject_unavailable_dependency_reviews(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(local_gate, '[]')
    result = run_gate(local_gate)

    assert result.returncode != 0
    assert 'Changed manifests require an available dependency review' in result.stderr


def test_local_checks_reject_unknown_vulnerability_data(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(local_gate, '[{"change_type":"added","vulnerabilities":null}]')
    result = run_gate(local_gate)

    assert result.returncode != 0
    assert 'Invalid dependency review data' in result.stderr


def test_local_checks_accept_reviewed_safe_dependency_changes(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(local_gate, '[{"change_type":"added","vulnerabilities":[]}]')
    result = run_gate(local_gate)
    _, output, _, _ = local_gate

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((output / 'dependency-review.json').read_text()) == [
        {'change_type': 'added', 'vulnerabilities': []}
    ]


def test_local_checks_preserve_the_existing_development_scope(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(
        local_gate,
        '[{"change_type":"added","scope":"development",'
        '"vulnerabilities":[{"severity":"low"}]}]',
    )
    result = run_gate(local_gate)

    assert result.returncode == 0, result.stdout + result.stderr
