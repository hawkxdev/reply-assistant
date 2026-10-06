---
name: implement-issue
description: >
  Implements one GitHub issue of this repository as one pull request. Use when asked to work on,
  implement or fix an issue, or when started by a comment on an issue.
---

# Implement issue

The issue is the contract. `AGENTS.md` holds the rules; this skill holds the order of work.

## Steps

1. Read the issue: goal, acceptance criteria, files in scope, files out of scope. Read the specification sections and supporting contracts the issue links to.
2. Stop and comment on the issue when a criterion cannot be verified or the work needs a protected path without the repository owner exception in **Boundaries**. Preserve explicit owner authority for an owner-prepared PR.
3. Work in a branch created from `main`. When the tool does not name it, use `feat/issue-<number>` or `fix/issue-<number>`.
4. The acceptance tests of the issue already cover its criteria. Write a new test only for behaviour they do not cover, and let it fail for the right reason before the code exists. A test that fails only together with an acceptance test is a duplicate: do not add it.
5. Write the smallest code that makes the test pass.
6. Run every command from **Commands** in `AGENTS.md`. Fix what fails. Do not change a test to make it pass.
7. For each new test break the code it guards, run the tests, confirm that this test fails, and restore the code. Note the defect for the pull request body.
8. Open the pull request. The title follows Conventional Commits; when the tool writes the title itself, put the correct title on the first line of the body. The body has four parts: **What changed**, **How verified** with the real output of the commands and, for each new test, the defect that makes it fail, **Out of scope** with findings that were not fixed, and `Closes #<number>`.
9. Add the label `agent-authored` when the tool allows it.

Implementation and checks run in the selected local harness. Use `scripts/check-local.sh` on the exact committed version and keep its result receipts. Read-only dependency comparison uses GitHub metadata, not Actions execution. Preserve configured provider-managed Codex review, assess each finding, and correct locally. Follow the owner-selected acceptance and merge authority without asking for routine steps again. The local workflow is defined in [local-workflow.md](../../../docs/local-workflow.md).

## Stop conditions

- The same check fails three times after three different fixes: stop and describe the failure in the pull request or on the issue.
- The change grows beyond the files named in the issue: stop and ask.

## Never

- Commit to `main`.
- Edit a path from **Boundaries** without its stated owner exception or the narrowly permitted `xfail` removal.
- Add a dependency the issue does not name.
- Report a check as passed without running it.


## Historical cloud correction and transfer

This section describes preserved cloud executions only. It does not select the archived author workflow or authorize new runner or model activity.

A correction starts only after the author workflow admits the owner's current-head request. Preserve the branch selected by the tool. The first and second reviews may return confirmed findings to the author; the third belongs to the lead for acceptance or bounded completion. Supplements on one commit share the same return.

The workflow records the actual published commit and remaining work. A successful job without preserved work is not delivery. For a takeover request finish or checkpoint the current operation, stop writing, and identify the saved commit and cloud run. Do not restart yourself or create another PR to reset the limit. Follow [ADR 0006](../../../docs/adr/0006-bounded-cloud-corrections.md); an unavailable checkpoint requires reconciliation.
