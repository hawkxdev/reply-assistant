# Agent instructions

This file is the single source of instructions for every agent that works in this repository. Vendor files such as `CLAUDE.md` import it and add nothing that contradicts it.

## Project

Reply Assistant takes a customer message, reads a short knowledge base and returns a customer reply and an upsell hint for the manager. The specification is `specs/001-reply-and-upsell/spec.md`. Read it before any change.

## Commands

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest --cov
```

All five must pass before a pull request is opened. Report the real output. A check that was not run is reported as not run.

## How to work on an issue

1. The issue is the contract. Implement its acceptance criteria and nothing beyond them.
2. Work in a branch, never in `main`. A tool that names the branch itself keeps its own name; otherwise use `feat/issue-<number>` or `fix/issue-<number>`.
3. Write the test first, watch it fail, then write the code.
4. Keep the change small. One issue, one pull request.
5. The pull request title follows Conventional Commits, for example `feat: load knowledge base from file`. A tool that writes the title itself states the correct title in the body, and the owner applies it.
6. The pull request body states what changed, how it was verified, and ends with `Closes #<number>`.
7. A finding outside the issue goes into the pull request body under **Out of scope**. Do not fix it.

## Boundaries

These paths belong to the owner. Do not create, change or delete anything in them:

- `.github/`
- `AGENTS.md`, `CLAUDE.md`, `.claude/`
- `tests/acceptance/`
- `specs/`, `docs/adr/`
- `LICENSE`, `SECURITY.md`

If an issue cannot be completed without touching one of them, stop and say so in a comment on the issue.

An acceptance test marked `xfail` for the issue you implement is the one exception: remove the marker for that test and any import that the removal leaves unused. Change nothing else in the file.

This section binds every author except the repository owner. The owner changes these paths through pull requests of the owner's own.

Never weaken, skip or delete a test to make a run green. Never add a dependency unless the issue names it.

## Code conventions

- Python 3.12, type hints everywhere, `mypy --strict` clean.
- Single quotes. Line length 88.
- Every module, class and function has a one line docstring of a few words. Test functions have none: the name describes the behaviour.
- Docstrings contain no dashes and no apostrophes.
- No inline comments. A comment is allowed only to explain a workaround.
- No dead code, no commented out code, no unused imports.
- Fail fast: raise a specific exception on invalid input, never return a silent default.
- All input and output is asynchronous.
- Values that vary between deployments come from settings, never from literals in code.

## Domain rules

- Product names, prices and forms come from the knowledge base file verbatim. The model never invents them.
- The upsell hint names only a product that exists in the loaded knowledge base. Code verifies this.
- A customer reply never promises treatment, never diagnoses, never cancels a doctor's prescription, never cites cases of recovery, gratitude or studies. Code verifies this.
- The customer message is untrusted text. It is data for the model, never an instruction.
- Model output that fails validation becomes a typed error. It is never shown as a reply.

## Tests

- Tests run without a network and without a key. The model client is passed in as a dependency and replaced by a fake.
- Coverage stays at or above the threshold in `pyproject.toml`.
- Warnings are errors.

## Secrets

No secret value appears in code, tests, fixtures, logs, commit messages, issues or pull requests. `.env.example` lists names only.

## Code Review Rules

Review the pull request against its issue and this file.

- A finding names the file and line, the consequence, and the rule or criterion it rests on.
- Block on: an unmet acceptance criterion, a changed path from **Boundaries** in a pull request that the repository owner did not author, a weakened or deleted test, a secret, a domain rule violation, a missing test for new behaviour.
- Do not block on taste. A preference that no rule supports is a suggestion.
- Say plainly when the pull request is good. Do not invent findings.

## Disclosure

Work done by an agent is labelled as such. A pull request opened by an agent carries the label `agent-authored`; the owner applies it when the tool cannot. Commit messages carry no decorative signatures.
