"""Conventions of tests and docstrings."""

import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple, TypeGuard

# === Rules ===

ROOTS = ('src', 'tests', 'scripts')
TESTS = Path('tests')
ACCEPTANCE = TESTS / 'acceptance'
FORBIDDEN_IN_DOCSTRING = re.compile("[\\-\u2010-\u2015'\u2018\u2019]")
ALLOWED_COMMENT = re.compile(
    r'# (=== \S.* ===|Step \d+: \S.*|Workaround\b.*\S'
    r'|type: ignore\[[a-z-]+(, ?[a-z-]+)*\]|noqa: [A-Z]+\d+(, ?[A-Z]+\d+)*)'
)
SKIPPING = {('pytest', 'skip'), ('pytest', 'importorskip'), ('mark', 'skip')}
SKIPPING |= {('mark', 'skipif')}
EXPECTED_FAILURE = {('pytest', 'xfail'), ('mark', 'xfail')}
ASSERTING_CALLS = {('pytest', 'raises'), ('pytest', 'warns')}

DocumentedNode = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


class Violation(NamedTuple):
    """One broken convention."""

    path: Path
    line: int
    code: str
    message: str

    def __str__(self) -> str:
        """Violation as report line."""
        return f'{self.path}:{self.line}: {self.code} {self.message}'


# === Helpers ===


def attribute_pair(node: ast.AST) -> tuple[str, str] | None:
    """Owner and name of attribute."""
    if not isinstance(node, ast.Attribute):
        return None
    owner = node.value
    if isinstance(owner, ast.Name):
        return owner.id, node.attr
    if isinstance(owner, ast.Attribute):
        return owner.attr, node.attr
    return None


def is_test_file(path: Path) -> bool:
    """Whether path holds tests."""
    return path.is_relative_to(TESTS)


def is_test_function(
    node: ast.AST, path: Path
) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Whether node is a test."""
    return (
        is_test_file(path)
        and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith('test')
    )


def is_constant_assertion(node: ast.Assert) -> bool:
    """Whether assert checks only constants."""
    test = node.test
    if isinstance(test, ast.Constant):
        return True
    if isinstance(test, ast.Compare):
        parts = [test.left, *test.comparators]
        return all(isinstance(part, ast.Constant) for part in parts)
    return False


def asserts_something(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether test body asserts."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if (
            isinstance(child, ast.Call)
            and attribute_pair(child.func) in ASSERTING_CALLS
        ):
            return True
    return False


def documented_nodes(tree: ast.Module) -> Iterator[DocumentedNode]:
    """Module, classes and functions."""
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


# === Checks ===


def check_docstrings(path: Path, tree: ast.Module) -> Iterator[Violation]:
    """Docstring presence and characters."""
    for node in documented_nodes(tree):
        line = getattr(node, 'lineno', 1)
        docstring = ast.get_docstring(node, clean=False)
        if is_test_function(node, path):
            if docstring is not None:
                yield Violation(path, line, 'C102', 'test function has a docstring')
            continue
        if docstring is None:
            yield Violation(path, line, 'C101', 'docstring is missing')
        elif FORBIDDEN_IN_DOCSTRING.search(docstring):
            yield Violation(path, line, 'C103', 'docstring has a dash or apostrophe')


def check_tests(path: Path, tree: ast.Module) -> Iterator[Violation]:
    """Markers and assertions of tests."""
    for node in ast.walk(tree):
        pair = attribute_pair(node)
        line = getattr(node, 'lineno', 1)
        if pair in SKIPPING:
            yield Violation(path, line, 'C201', 'test is skipped')
        if pair in EXPECTED_FAILURE and not path.is_relative_to(ACCEPTANCE):
            yield Violation(path, line, 'C202', 'xfail outside acceptance tests')
        if isinstance(node, ast.Assert) and is_constant_assertion(node):
            yield Violation(path, line, 'C204', 'assertion on a constant')
        if is_test_function(node, path) and not asserts_something(node):
            yield Violation(path, line, 'C203', 'test asserts nothing')


def check_comments(path: Path, source: str) -> Iterator[Violation]:
    """Comments of allowed kinds."""
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type == tokenize.COMMENT and not ALLOWED_COMMENT.fullmatch(
            token.string
        ):
            yield Violation(path, token.start[0], 'C301', 'comment is not allowed')


def check_source(path: Path, source: str) -> list[Violation]:
    """Every check on one file."""
    tree = ast.parse(source, filename=str(path))
    violations = [*check_docstrings(path, tree), *check_comments(path, source)]
    if is_test_file(path):
        violations.extend(check_tests(path, tree))
    return sorted(violations, key=lambda violation: (violation.line, violation.code))


# === Entry point ===


def main(root: Path) -> int:
    """Check the repository tree."""
    files = sorted(
        path.relative_to(root)
        for folder in ROOTS
        for path in (root / folder).rglob('*.py')
    )
    violations = [
        violation
        for path in files
        for violation in check_source(path, (root / path).read_text(encoding='utf-8'))
    ]
    for violation in violations:
        print(violation)
    print(f'checked {len(files)} files, {len(violations)} violations')
    return 1 if violations or not files else 0


if __name__ == '__main__':
    sys.exit(main(Path.cwd()))
