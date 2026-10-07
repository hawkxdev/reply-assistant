# Implementation knowledge

The [implementation role](../../.claude/skills/implement-issue/SKILL.md) owns use of these project gates. [AGENTS.md](../../AGENTS.md) owns shared constraints; the feature contract owns behavior.

## Reply service and page

[Feature 001](../../specs/001-reply-and-upsell/spec.md) is the service contract. Generation passes the loaded catalogue and untrusted customer text to a model client, then validates shape, product identity and forbidden claims before returning a reply. The model client is injected for offline tests. Catalogue replacement must not require a code change.

The page is `src/reply_assistant/static/index.html`, a static document without a frontend build. Page tests invoke JavaScript through Node.js. Browser measurements, synthetic interactions and model-provider calls are separate observations with separate authorization. A fixed viewport or an element class alone does not prove responsive behavior; retain the actual dimensions and inspected result for an authorized UI task.

## Offline evaluator

[Feature 002](../../specs/002-grounded-product-replies/spec.md) and its linked plan, rules and corpus format own evaluation. Recorded replies are assessed under versioned semantic rules. This component does not change provider generation, response validation or the historical T11 exact-match contract. Corpus and rule changes need their own pinned inputs; a result from another version is not current evidence.

## Organizational retirement

[ADR 0008](../adr/0008-local-project-knowledge.md) retires the disabled cloud author mechanism. Its unused adapters and infrastructure tests retain their exact source in Git history, while the shared coordination implementation remains outside the outgoing tree. There is no replacement project loader or private archive. Product and acceptance tests remain in this repository. A structural or import check proves only that part of the retirement; it is not a product test result.
