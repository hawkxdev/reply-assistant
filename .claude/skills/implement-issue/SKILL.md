---
name: implement-issue
description: >
  WHEN: реализуй/реализовывай issue Reply Assistant, исправь/исправляй продукт по принятой задаче, implement an assigned Reply Assistant issue. WHEN NOT: recover the project without a task (project-brain), assess another version (review-pull-request).
allowed-tools: [Read, Grep, Bash, Edit, Write]
---

# Reply Assistant implementation gates

## Degrees of Freedom: LOW

## Accountability

Implement the assigned issue within its source version and permitted paths. This role owns project-specific implementation decisions and reports evidence to the lead; it does not accept its own work independently or grant publication, merge, provider calls or deployment.

Read the issue, [AGENTS.md](../../../AGENTS.md) and [the knowledge shelf](references/kb-index.md). The issue supplies scope; the specification supplies product requirements. Use [project-brain](../project-brain/SKILL.md) if those owners are unclear. A bare invocation without an assignment recovers that context and asks which issue is intended; a historical handoff is not an assignment.

## Project gates

[Implementation knowledge](../../../docs/knowledge/implementation.md) maps the service, evaluator and page to their requirements and tests. Read the applicable section before editing. AGENTS.md owns protected paths, domain validation, the six local commands, test uniqueness and disclosure; do not recreate their general workflow here.

Acceptance tests may already cover an issue. New tests must identify a distinct observable defect and preserve the exact-match and no-network contracts. Product names, forms and prices come from the loaded catalogue; the offline evaluator does not loosen generation checks. A blocked protected-path change or unavailable required observation goes to the lead with its affected criterion. Continue only independent in-scope work.

If the same required check fails after three distinct fixes, return the observed failure to the lead. Work that grows beyond the issue stops at its scope boundary.

## Result and upkeep

Return the exact version, changed paths, criterion evidence and limitations to the lead through the task's assigned channel. A command not run is not passing, and a preserved branch is not accepted delivery. An explicit inspection-only or test restriction remains binding. Maintain product details at the specification or implementation knowledge; changes to the gate itself belong here and in its shelf backlink.

## Harness enhancements

Use the current local harness and existing project commands. No cloud launch, reviewer request or observer is part of this role. Missing tools produce a named limitation, not a replacement execution route.

## Rationalization Table

| Excuse | Project consequence |
|---|---|
| Evaluator checks already passed | They do not replace response validation or exact catalogue facts. |
| An acceptance test exists, so another is needed | Add only a test for a distinct defect not caught by that acceptance test. |

## Red Flags

- A catalogue fact is generated instead of loaded verbatim.
- A stopped task or protected-path change is resumed without its authority.
