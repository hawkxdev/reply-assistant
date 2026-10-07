# Review knowledge

The [review role](../../.claude/skills/review-pull-request/SKILL.md) owns use of these project checks. [AGENTS.md](../../AGENTS.md) owns findings and acceptance gates.

## Product boundaries

For service changes, follow customer text through prompt construction, model-client injection and response validation. Check that a rejected reply never escapes as customer output, that catalogue facts retain their exact spelling and that upsells name existing products. Do not substitute an evaluator score for these service invariants.

For evaluator changes, read the versioned feature 002 rules and corpus owner. A test must distinguish a real defect without computing its expected answer through the implementation. Recorded corpus coverage does not prove live provider behavior.

For page changes, separate draft editing, customer input and suggestion insertion. Confirm authorized UI evidence preserves text, selection, logical scroll and reachable controls across modes and languages. Source declarations alone do not establish geometry.

## Organizational changes

Read the specific retirement contract and [ADR 0008](../adr/0008-local-project-knowledge.md). Follow every removed import to its remaining caller and compare the unaffected source/test tree. Tests that belong exclusively to a retired cloud mechanism may move only under explicit owner authority with their source preserved. Never use this exception to weaken a product invariant or claim an unrun suite passed.

Current-head evidence and preservation are different from independent review. Historical review metadata, a completed workflow or an author report do not establish current acceptance. Provider reviews and old findings require active authorization even when an integration is retained.
