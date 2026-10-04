---
name: review-pull-request
description: >
  Reviews a pull request of this repository against its issue and AGENTS.md. Use when asked to
  review a pull request or when started by a review request.
---

# Review pull request

The reviewer checks the work of another agent. It does not fix the code and does not extend the contract.

## Steps

1. Read the pull request body and the issue it closes. No linked issue means no contract: say so and review against `AGENTS.md` only.
2. Read the diff. List the changed files and compare them with the files in scope of the issue.
3. For each acceptance criterion find the code that implements it and the test that would fail without it. A criterion with no such test is a finding.
4. Check **Boundaries** in `AGENTS.md`. In a pull request that the repository owner did not author, a changed owner path is a blocking finding, apart from a removed `xfail` marker of the acceptance test of this issue and an import that the removal left unused.
5. Check the tests: nothing deleted, skipped or loosened; no network; no secret in fixtures. For each new test find the defect named in the body and check that no other test already fails on it. Apply the rest of **Tests** in `AGENTS.md`.
6. Check the domain rules in `AGENTS.md`.
7. Write the review by **Code Review Rules** in `AGENTS.md`.

## Verdict

- Every criterion covered and no blocking finding: approve in words.
- A blocking finding: request changes and name each one.
- Not enough evidence: say what could not be verified and why.

The verdict is advice. The lead agent merges.


## Bounded review

The lead verifies advice and records confirmed findings against the exact reviewed commit. A reviewer comment does not authorize an author launch. The first review covers the whole contract; the second checks corrections and affected behavior. Supplements and redelivery on the same commit do not create another correction return.

At the third review accept a correct version, or freeze the remaining confirmed findings for the lead. Do not ask the author for a third return or add another mandatory review cycle. Changes made by the lead are self-verified with the same criteria. Handoff is not acceptance; an unfinished remainder needs a specific blocker and recommendation. Procedure: [ADR 0006](../../../docs/adr/0006-bounded-cloud-corrections.md).
