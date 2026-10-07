# Agent instructions

This file is the single source of instructions for every agent that works in this repository. Vendor files such as `CLAUDE.md` import it and add nothing that contradicts it.

## Project

Reply Assistant takes a customer message, reads a short knowledge base and returns a customer reply and an upsell hint for the manager. The specification is `specs/001-reply-and-upsell/spec.md`. Read it before any change.

The separate offline quality evaluator is specified in `specs/002-grounded-product-replies/spec.md`. For an issue about that evaluator, also read its linked plan, rules and corpus format. Feature 002 assesses recorded answers under versioned semantic rules; it does not change generation, service checks or the historical T11 exact-match contract.

## Commands

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest --cov
uv run python scripts/check_conventions.py
```

All six must pass before a product pull request is opened. A specifically owner-authorized organizational retirement uses its stated structural, import and preservation checks; the five retired infrastructure modules in ADR 0008 retain their exact source in Git history. This exception does not waive product verification or coverage for product changes. Report the actual checks; an omitted suite is not passing.

For the complete local entry, see [docs/local-workflow.md](docs/local-workflow.md). Run `bash scripts/check-local.sh --base <base-commit> --title <PR-title>` from a clean committed checkout. It includes all six commands and records the exact inputs and failures.

## How to work on an issue

1. The issue is the contract. Implement its acceptance criteria and nothing beyond them.
2. Work in a branch, never in `main`. A tool that names the branch itself keeps its own name; otherwise use `feat/issue-<number>` or `fix/issue-<number>`.
3. Write the test first, watch it fail, then write the code.
4. Keep the change small. One issue, one pull request.
5. The pull request title follows Conventional Commits, for example `feat: load knowledge base from file`. A tool that writes the title itself states the correct title in the body, and the lead agent applies it.
6. The pull request body states what changed, how it was verified, and ends with `Closes #<number>`.
7. A finding outside the issue goes into the pull request body under **Out of scope**. Do not fix it.

## Execution and knowledge

Work locally under the assigned task. Repository Actions execution is disabled; do not dispatch or restore excluded executors, checks, builds or deployment. Cloud reviews and processing of old findings are stopped even where an existing reviewer connection is retained. A historical receipt or skill never resumes an old task.

Project navigation belongs to [.claude/skills/project-brain/SKILL.md](.claude/skills/project-brain/SKILL.md); recipient-accessible details belong to [docs/knowledge/README.md](docs/knowledge/README.md). Shared methodology and canonical helpers are not published here. The retired author mechanism and preserved historical project contract are described in [ADR 0008](docs/adr/0008-local-project-knowledge.md). Earlier cloud ADRs remain historical sources.

## Boundaries

These paths belong to the owner. Do not create, change or delete anything in them:

- `.github/`
- `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`
- `tests/acceptance/`
- `scripts/check-local.sh`, `scripts/archived-workflows/`
- `tests/test_local_checks.py`, `docs/local-workflow.md`
- `specs/`, `docs/adr/`, `docs/knowledge/`
- `LICENSE`, `SECURITY.md`

If an issue cannot be completed without touching one of them, stop and say so in a comment on the issue.

An acceptance test marked `xfail` for the issue you implement is the one exception: remove the marker for that test and any import that the removal leaves unused. Change nothing else in the file.

This section binds every author except the repository owner. The owner changes these paths through pull requests of the owner's own. A pull request opened from the owner's account is the owner's, including one prepared by the lead agent and labelled `agent-authored` (see `docs/adr/0004-lead-agent.md`).

Never weaken, skip or delete a test to make a run green. Never add a dependency unless the issue names it.

## Code conventions

- Python 3.12, type hints everywhere, `mypy --strict` clean.
- Single quotes. Line length 88.
- Every module, class and function has a docstring. Test functions have none: the name describes the behaviour.
- A docstring is one line of three or four words. More words only when fewer lose the purpose, a second line only when it cannot be avoided, an example only when the format is not clear from the signature.
- Docstrings contain no dash of any kind and no apostrophe.
- A comment is one of three kinds: a section separator `# === Name ===`, a pipeline step `# Step 1: ...`, a workaround `# Workaround ...`. A file with several logical zones has section separators. A type or lint pragma names its code.
- No dead code, no commented out code, no unused imports.
- Fail fast: raise a specific exception on invalid input, never return a silent default.
- All input and output is asynchronous.
- Values that vary between deployments come from settings, never from literals in code.

`scripts/check_conventions.py` checks the presence of docstrings, their characters and the kinds of comments. Review checks the length of docstrings and the section separators.

## Domain rules

- Product names, prices and forms come from the knowledge base file verbatim. The model never invents them.
- The upsell hint names only a product that exists in the loaded knowledge base. Code verifies this.
- A customer reply never promises treatment, never diagnoses, never cancels a doctor's prescription, never cites cases of recovery, gratitude or studies. Code verifies this.
- The customer message is untrusted text. It is data for the model, never an instruction.
- Model output that fails validation becomes a typed error. It is never shown as a reply.

## Tests

- Tests run without a network and without a key. The model client is passed in as a dependency and replaced by a fake.
- Coverage stays at or above the threshold in `pyproject.toml`. Coverage is not a goal: a test that exists only for coverage is removed.
- Warnings are errors.

A test is kept only if it can fail:

- It fails on a defect that no other test catches. For each new test the pull request body names that defect: break the code, watch this test fail, restore the code.
- It asserts. An assertion on a constant is not an assertion.
- Expected values are literals, never computed by the code under test.
- It tests this code, not the language, the standard library or a dependency. A test that a declared annotation, default or base class is what it says proves the declaration, not behaviour.
- It runs. No skipped tests. `xfail` exists only in `tests/acceptance`, until the issue that removes it.

`scripts/check_conventions.py` checks skipped tests, the place of `xfail`, tests without an assertion and assertions on a constant. Review checks the rest.

## Secrets

No secret value appears in code, tests, fixtures, logs, commit messages, issues or pull requests. `.env.example` lists names only.

## Code Review Rules

Review the pull request against its issue and this file.

- A finding names the file and line, the consequence, and the rule or criterion it rests on.
- Block on: an unmet acceptance criterion, a changed path from **Boundaries** in a pull request that the repository owner did not author, a weakened or deleted product test or infrastructure test retired without an explicit contract and preserved source, a test that cannot fail on a defect no other test catches, a missing named defect for a new test, a secret, a domain rule violation, a missing test for new behaviour.
- Do not block on taste. A preference that no rule supports is a suggestion.
- Say plainly when the pull request is good. Do not invent findings.

## Disclosure

Work done by an agent is labelled as such. A pull request opened by an agent carries the label `agent-authored`, a pull request of the lead agent included; the lead agent applies it when the tool cannot. Commit messages carry no decorative signatures.
