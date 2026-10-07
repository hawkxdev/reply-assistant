---
name: project-brain
description: >
  WHEN: начни/начинай работу в Reply Assistant, восстанови/восстанавливай контекст проекта, navigate Reply Assistant or recover its project context. WHEN NOT: implement an assigned issue (implement-issue), evaluate an assigned PR (review-pull-request).
allowed-tools: [Read, Grep, Bash]
---

# Reply Assistant navigation

## Degrees of Freedom: MEDIUM

## Accountability

Identify the current project contract and permitted next operation. This role owns navigation and source selection, not generation, quality rules, implementation or release approval. Completion means the task, source version, working-copy ownership and unresolved dependencies are explicit.

## Entry

Read [AGENTS.md](../../../AGENTS.md) and the [knowledge shelf](references/kb-index.md). Establish the actual checkout and relevant issue before treating a handoff or an old decision as current. An assigned task goes directly to its project owner below. A bare entry without a task recovers context, then offers product implementation, evaluator work or project knowledge maintenance and asks which is intended. Prior work never starts from navigation alone.

## Project owners

- For reply generation, HTTP or page behavior, read [feature 001](../../../specs/001-reply-and-upsell/spec.md), then use [implement-issue](../implement-issue/SKILL.md) for the project gates.
- For offline answer assessment, read [feature 002](../../../specs/002-grounded-product-replies/spec.md) and its linked plan, rules and corpus format. Its evaluator does not change generation or historical exact-match acceptance.
- For an assigned PR assessment, use [review-pull-request](../review-pull-request/SKILL.md). Its advice does not authorize merge, cloud execution or deployment.
- For collaboration and execution boundaries, read [the working process](../../../docs/how-this-repo-is-built.md). For retired cloud mechanisms, read [ADR 0008](../../../docs/adr/0008-local-project-knowledge.md); earlier ADRs are historical context.

## Access and upkeep

Public tasks must be understandable from recipient-accessible sources. Missing private operational context blocks only the operation that needs it; never copy internal methods into this role. Preserve explicit stops and unrelated work. Correct navigation at this role, product requirements at the feature owner and shared project rules at AGENTS.md. Report a missing source or conflict to the project lead instead of inventing its contents.

## Harness enhancements

Use available file and Git inspection tools. Filesystem links prove source availability, not that a fresh agent followed them. Do not start another agent or review as a context-recovery step.
