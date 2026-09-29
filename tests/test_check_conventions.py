"""Convention checker tests."""

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

# === Loading ===

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'check_conventions.py'


def load_checker() -> ModuleType:
    """Import the checker script."""
    spec = importlib.util.spec_from_file_location('check_conventions', SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def findings(path: str, source: str) -> list[tuple[int, str]]:
    """Lines and codes found."""
    violations = checker.check_source(Path(path), dedent(source).lstrip())
    return [(violation.line, violation.code) for violation in violations]


# === Docstrings ===


def test_clean_source_has_no_findings() -> None:
    source = '''
        """Clean module."""


        class Box:
            """Holds a value."""

            def value(self) -> int:
                """Stored value."""
                return 1
    '''

    assert findings('src/box.py', source) == []


@pytest.mark.parametrize(
    ('source', 'line'),
    [
        ('x = 1\n', 1),
        ('"""Module."""\n\n\ndef run() -> None:\n    return None\n', 4),
        ('"""Module."""\n\n\nclass Box:\n    size = 1\n', 4),
    ],
    ids=['module', 'function', 'class'],
)
def test_missing_docstring_is_found(source: str, line: int) -> None:
    assert findings('src/box.py', source) == [(line, 'C101')]


@pytest.mark.parametrize(
    'docstring', ['Read-only view.', 'Box \u2013 value.', 'Box \u2014 value.']
)
def test_dash_in_docstring_is_found(docstring: str) -> None:
    source = f'"""{docstring}"""\n'

    assert findings('src/box.py', source) == [(1, 'C103')]


@pytest.mark.parametrize('docstring', ["Box's value.", 'Box\u2019s value.'])
def test_apostrophe_in_docstring_is_found(docstring: str) -> None:
    source = f'"""{docstring}"""\n'

    assert findings('src/box.py', source) == [(1, 'C103')]


def test_docstring_on_test_function_is_found() -> None:
    source = '''
        """Box tests."""


        def test_box() -> None:
            """Box works."""
            assert box() == 1
    '''

    assert findings('tests/test_box.py', source) == [(4, 'C102')]


def test_function_named_test_outside_tests_needs_docstring() -> None:
    source = '''
        """Module."""


        def test_mode() -> bool:
            return True
    '''

    assert findings('src/box.py', source) == [(4, 'C101')]


# === Tests ===


@pytest.mark.parametrize(
    'statement',
    [
        '@pytest.mark.skip(reason="later")',
        '@pytest.mark.skipif(True, reason="later")',
    ],
)
def test_skip_marker_is_found(statement: str) -> None:
    source = (
        f'"""Box tests."""\n\n\n{statement}\n'
        'def test_box() -> None:\n    assert box() == 1\n'
    )

    assert findings('tests/test_box.py', source) == [(4, 'C201')]


@pytest.mark.parametrize(
    'statement', ['pytest.skip("later")', 'pytest.importorskip("yaml")']
)
def test_skip_call_is_found(statement: str) -> None:
    source = (
        '"""Box tests."""\n\n\ndef test_box() -> None:\n'
        f'    {statement}\n    assert box() == 1\n'
    )

    assert findings('tests/test_box.py', source) == [(5, 'C201')]


def test_xfail_outside_acceptance_is_found() -> None:
    source = '"""Box tests."""\n\npytestmark = pytest.mark.xfail(strict=True)\n'

    assert findings('tests/test_box.py', source) == [(3, 'C202')]
    assert findings('tests/acceptance/test_box.py', source) == []


def test_test_without_assertion_is_found() -> None:
    source = '''
        """Box tests."""


        def test_box() -> None:
            box()
    '''

    assert findings('tests/test_box.py', source) == [(4, 'C203')]


def test_raises_counts_as_assertion() -> None:
    source = '''
        """Box tests."""


        def test_box() -> None:
            with pytest.raises(BoxError, match='empty'):
                box()
    '''

    assert findings('tests/test_box.py', source) == []


@pytest.mark.parametrize('assertion', ['assert True', 'assert 1 == 1'])
def test_assertion_on_constant_is_found(assertion: str) -> None:
    source = (
        f'"""Box tests."""\n\n\ndef test_box() -> None:\n    box()\n    {assertion}\n'
    )

    assert findings('tests/test_box.py', source) == [(6, 'C204')]


# === Comments ===


@pytest.mark.parametrize(
    'comment',
    [
        '# === Data ===',
        '# Step 1: Load the file',
        '# Workaround for issue 12',
        '# type: ignore[call-arg]',
        '# noqa: S101',
    ],
)
def test_allowed_comment_passes(comment: str) -> None:
    source = f'"""Module."""\n\n{comment}\nx = 1\n'

    assert findings('src/box.py', source) == []


@pytest.mark.parametrize(
    'comment', ['# increment the counter', '# type: ignore', '# noqa', '# TODO later']
)
def test_other_comment_is_found(comment: str) -> None:
    source = f'"""Module."""\n\n{comment}\nx = 1\n'

    assert findings('src/box.py', source) == [(3, 'C301')]


# === Entry point ===


def test_main_reports_counts_and_fails_on_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'box.py').write_text('x = 1\n', encoding='utf-8')

    assert checker.main(tmp_path) == 1
    assert capsys.readouterr().out.splitlines() == [
        'src/box.py:1: C101 docstring is missing',
        'checked 1 files, 1 violations',
    ]


def test_main_passes_clean_tree(tmp_path: Path) -> None:
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'box.py').write_text('"""Box."""\n', encoding='utf-8')

    assert checker.main(tmp_path) == 0


def test_main_fails_when_nothing_is_checked(tmp_path: Path) -> None:
    assert checker.main(tmp_path) == 1
