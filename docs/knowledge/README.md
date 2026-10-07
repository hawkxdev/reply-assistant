# Project knowledge

This shelf contains recipient-accessible Reply Assistant knowledge. Role rules and navigation belong to [project-brain](../../.claude/skills/project-brain/SKILL.md), [implement-issue](../../.claude/skills/implement-issue/SKILL.md) and [review-pull-request](../../.claude/skills/review-pull-request/SKILL.md). Technical details below remain with their own documents; shared project constraints belong to [AGENTS.md](../../AGENTS.md).

| Need | Owner | Read when |
|---|---|---|
| Project entry and source selection | project-brain | A task starts or the contract is unclear |
| Service, evaluator and page implementation details | [implementation.md](implementation.md) | Before an assigned change |
| Project failure boundaries and evidence limits | [review.md](review.md) | Before an assigned version assessment |
| Local verification and release preparation | [local-workflow.md](../local-workflow.md) | Before local acceptance or a separately authorized release |
| Current collaboration route | [how-this-repo-is-built.md](../how-this-repo-is-built.md) | Execution or delivery authority matters |
| Product requirements and architecture | [specifications](../../specs/001-reply-and-upsell/spec.md), [decision records](../adr/0008-local-project-knowledge.md) | The relevant feature or historical decision is needed |

This shelf is not a task-status ledger, a catalogue of private methods or a deployment access record. Fix a technical detail at its owner; update the role pointer and this backlink together when navigation changes. Public knowledge must remain usable without the owner's private working environment.
