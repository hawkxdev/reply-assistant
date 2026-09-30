"""Live command unit tests."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

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
