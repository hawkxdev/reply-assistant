# 0005. Conventions are checked by a script, not only written down

## Context

Agents write most of the tests in this repository. An agent asked to test a criterion tends to add tests that cannot fail on their own: a check that a declared annotation is what it says, a copy of an acceptance test, a call with no assertion. Such tests raise the coverage number and prove nothing. The first author pull request, #10, added three of them.

The rules against them were a paragraph in `AGENTS.md`. An instruction file steers an agent and enforces nothing.

## Decision

- `AGENTS.md` states the rules for tests, docstrings and comments in a few checkable lines.
- `scripts/check_conventions.py` enforces the part that a machine can decide: skipped tests, `xfail` outside `tests/acceptance`, tests without an assertion, assertions on a constant, missing docstrings, a docstring on a test function, dashes and apostrophes in docstrings, comments of a kind that is not allowed. It runs as the required check **Conventions** on every pull request, whoever the author is.
- The reviewer agent checks the part that needs judgement: duplicates, tests of a dependency, docstring length, section separators.
- A new test must be able to fail on a defect no other test catches, and the pull request names that defect. This is the one proof that a test is useful: break the code, watch the test fail.
- Before the repository is shown to anyone, an independent agent of the owner audits the tests by a fixed procedure. Its findings are a reason to strengthen the script or the review rules.
- The script is tested like any other code: every rule has a sample it must reject, and each rule was removed from the script once to see its test fail.

## Alternatives

| Alternative | Why not |
|---|---|
| Rules in `AGENTS.md` only | They hold only while every agent reads and follows them |
| Mutation testing on every pull request | The strongest proof, but it adds a dependency and minutes to each run; revisited when the service grows |
| `pydocstyle` rules of `ruff` for docstrings | They cover presence and form, not the dash, the apostrophe or the test function rule, so a script is needed anyway |

## Consequences

- A pull request with a skipped test or a test without an assertion cannot be merged.
- Three tests of #10 that never failed alone were removed.
- The script is small and has no dependency. When a rule is added to `AGENTS.md` and a machine can decide it, the rule is added to the script with a sample it must reject.
