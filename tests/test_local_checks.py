"""Verify local gate orchestration."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# === Fixture preparation ===


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


def prepare_repository(root: Path) -> None:
    """Prepare the repository template."""
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
    git(root, 'remote', 'add', 'origin', 'https://github.com/fixture/repo.git')


@pytest.fixture(scope='session')
def local_gate_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Prepare the shared template."""
    root = tmp_path_factory.mktemp('local-gate-template') / 'repo'
    prepare_repository(root)
    return root


def prepare_local_gate(
    template: Path, tmp_path: Path
) -> tuple[Path, Path, str, dict[str, str]]:
    """Prepare isolated gate inputs."""
    root = tmp_path / 'repo'
    shutil.copytree(template, root)
    base = git(root, 'rev-parse', 'HEAD')
    tools = tmp_path / 'tools'
    tools.mkdir()
    uv = tools / 'uv'
    uv.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$*" >> "$LOCAL_UV_LOG"\n'
        'if [ "$*" = "run ruff check ." ] '
        '&& [ "${LOCAL_FAIL_RUFF:-0}" = "1" ]; then exit 23; fi\n'
        'if [ "$*" = "run python scripts/check_conventions.py" ]; then\n'
        'case "${LOCAL_MUTATION:-}" in\n'
        'dirty) printf "\\n" >> pyproject.toml ;;\n'
        'head) git -c commit.gpgsign=false commit -q --allow-empty '
        '-m "chore: fixture drift" ;;\n'
        'esac\nfi\n'
        'exit 0\n'
    )
    uv.chmod(0o700)
    gh = tools / 'gh'
    gh.write_text(
        '#!/bin/sh\ncat "$LOCAL_REVIEW_INPUT"\n'
        'if [ "${LOCAL_REVIEW_FAIL:-0}" = "1" ]; then\n'
        'echo "Dependency comparison unavailable." >&2\nexit 19\nfi\n'
    )
    gh.chmod(0o700)
    env = {
        key: os.environ[key]
        for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT')
        if key in os.environ
    }
    env.update(PATH=f'{tools}:{env["PATH"]}', LOCAL_UV_LOG=str(tmp_path / 'uv.log'))
    return root, tmp_path / 'result', base, env


@pytest.fixture
def local_gate(
    local_gate_template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str, dict[str, str]]:
    """Prepare isolated gate inputs."""
    monkeypatch.setenv('LOCAL_PARENT_CANARY', 'fixture-marker')
    return prepare_local_gate(local_gate_template, tmp_path)


def gate_pair(
    template: Path, tmp_path: Path
) -> tuple[
    tuple[Path, Path, str, dict[str, str]], tuple[Path, Path, str, dict[str, str]]
]:
    """Prepare two independent gates."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    return prepare_local_gate(template, first), prepare_local_gate(template, second)


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


# === Gate behavior ===


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
    _, output, _, env = local_gate
    env['LOCAL_REVIEW_FAIL'] = '1'
    result = run_gate(local_gate)

    assert result.returncode == 19
    assert 'Dependency comparison unavailable' in result.stderr
    assert (output / 'exit-code.txt').read_text() == '19\n'


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


def test_local_checks_accept_a_successful_empty_dependency_diff(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    change_dependencies(local_gate, '[]')
    result = run_gate(local_gate)
    _, output, _, _ = local_gate

    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / 'exit-code.txt').read_text() == '0\n'
    assert json.loads((output / 'dependency-review.json').read_text()) == []


@pytest.mark.parametrize('mutation', ['head', 'dirty'])
def test_local_checks_reject_inputs_changed_during_execution(
    local_gate: tuple[Path, Path, str, dict[str, str]], mutation: str
) -> None:
    _, output, base, env = local_gate
    env['LOCAL_MUTATION'] = mutation
    result = run_gate(local_gate)

    assert result.returncode == 1
    assert (output / 'commit.txt').read_text().strip() == base
    assert (output / 'exit-code.txt').read_text() == '1\n'
    assert 'Checked inputs changed during verification' in result.stderr


def test_local_checks_exclude_unrelated_parent_environment(
    local_gate: tuple[Path, Path, str, dict[str, str]],
) -> None:
    _, _, _, env = local_gate

    assert 'LOCAL_PARENT_CANARY' not in env


# === Fixture isolation ===


def test_local_gate_repository_changes_stay_in_own_copy(
    local_gate_template: Path, tmp_path: Path
) -> None:
    first, second = gate_pair(local_gate_template, tmp_path)
    template_head = git(local_gate_template, 'rev-parse', 'HEAD')
    root, _, base, _ = first
    (root / 'tests' / 'existing.py').write_text('existing = False\n')
    git(root, 'add', '.')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'chore: fixture change')
    git(root, 'branch', 'fixture-probe')
    git(root, 'config', 'user.name', 'Changed')
    git(root, 'remote', 'set-url', 'origin', 'https://github.com/fixture/changed.git')

    assert git(root, 'rev-parse', 'HEAD') != base
    assert git(root, 'config', 'user.name') == 'Changed'
    for survivor, expected_head in (
        (second[0], second[2]),
        (local_gate_template, template_head),
    ):
        assert (survivor / 'tests' / 'existing.py').read_text() == 'existing = True\n'
        assert git(survivor, 'rev-parse', 'HEAD') == expected_head
        assert git(survivor, 'status', '--porcelain') == ''
        assert 'fixture-probe' not in git(survivor, 'branch', '--list')
        assert git(survivor, 'config', 'user.name') == 'Fixture'
        assert git(survivor, 'remote', 'get-url', 'origin') == (
            'https://github.com/fixture/repo.git'
        )
    result = run_gate(second)
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_gate_command_stubs_are_independent(
    local_gate_template: Path, tmp_path: Path
) -> None:
    first, second = gate_pair(local_gate_template, tmp_path)
    tools = Path(first[3]['PATH'].split(os.pathsep)[0])
    (tools / 'uv').write_text('#!/bin/sh\nexit 41\n')
    (tools / 'gh').write_text('#!/bin/sh\nexit 42\n')
    failed = run_gate(first)
    change_dependencies(second, '[]')
    result = run_gate(second)

    assert failed.returncode == 41
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_gate_environments_are_independent(
    local_gate_template: Path, tmp_path: Path
) -> None:
    first, second = gate_pair(local_gate_template, tmp_path)
    first[3]['LOCAL_FAIL_RUFF'] = '1'
    failed = run_gate(first)
    result = run_gate(second)

    assert failed.returncode == 23
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_gate_artifacts_are_independent(
    local_gate_template: Path, tmp_path: Path
) -> None:
    first, second = gate_pair(local_gate_template, tmp_path)
    original = run_gate(first)
    change_dependencies(second, '[]')
    changed_head = git(second[0], 'rev-parse', 'HEAD')
    result = run_gate(second)

    assert original.returncode == 0, original.stdout + original.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert (first[1] / 'commit.txt').read_text().strip() == first[2]
    assert (second[1] / 'commit.txt').read_text().strip() == changed_head
    assert (first[1] / 'exit-code.txt').read_text() == '0\n'
    assert (second[1] / 'exit-code.txt').read_text() == '0\n'
    assert Path(first[3]['LOCAL_UV_LOG']).read_text().splitlines() == [
        'sync --locked',
        'run ruff check .',
        'run ruff format --check .',
        'run mypy .',
        'run pytest --cov',
        'run python scripts/check_conventions.py',
    ]
    assert Path(second[3]['LOCAL_UV_LOG']).read_text().splitlines() == [
        'sync --locked',
        'run ruff check .',
        'run ruff format --check .',
        'run mypy .',
        'run pytest --cov',
        'run python scripts/check_conventions.py',
    ]
