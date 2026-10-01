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
2. Stop and comment on the issue when a criterion cannot be verified by a command or an observation, or when the work needs a path from **Boundaries** in `AGENTS.md`.
3. Work in a branch created from `main`. When the tool does not name it, use `feat/issue-<number>` or `fix/issue-<number>`.
4. The acceptance tests of the issue already cover its criteria. Write a new test only for behaviour they do not cover, and let it fail for the right reason before the code exists. A test that fails only together with an acceptance test is a duplicate: do not add it.
5. Write the smallest code that makes the test pass.
6. Run every command from **Commands** in `AGENTS.md`. Fix what fails. Do not change a test to make it pass.
7. For each new test break the code it guards, run the tests, confirm that this test fails, and restore the code. Note the defect for the pull request body.
8. Open the pull request. The title follows Conventional Commits; when the tool writes the title itself, put the correct title on the first line of the body. The body has four parts: **What changed**, **How verified** with the real output of the commands and, for each new test, the defect that makes it fail, **Out of scope** with findings that were not fixed, and `Closes #<number>`.
9. Add the label `agent-authored` when the tool allows it.

## Stop conditions

- The same check fails three times after three different fixes: stop and describe the failure in the pull request or on the issue.
- The change grows beyond the files named in the issue: stop and ask.

## Never

- Commit to `main`.
- Edit a path from **Boundaries**, apart from removing the `xfail` marker of the acceptance test of this issue together with an import the removal leaves unused.
- Add a dependency the issue does not name.
- Report a check as passed without running it.
