# Tasks 001: reply and upsell hint

Each task becomes one issue and one pull request. Requirement numbers refer to [`spec.md`](spec.md).

The lead agent fills the **Issue** column when it opens the issue of a task, in the pull request that adds the acceptance tests. The state of that issue is the state of the task: open while the work goes on, closed when the implementation is merged.

| Task | Result | Requirements | Issue |
|---|---|---|---|
| T1 | Settings module and `.env.example` in step | R17, R29 | [#7](https://github.com/hawkxdev/reply-assistant/issues/7) |
| T2 | Knowledge base schema, loader and two example files | R1 to R5 | [#14](https://github.com/hawkxdev/reply-assistant/issues/14) |
| T3 | Suggestion schema and prompt builder | R6 to R8, R12 | [#16](https://github.com/hawkxdev/reply-assistant/issues/16) |
| T4 | Checks by code | R9 to R11 | [#19](https://github.com/hawkxdev/reply-assistant/issues/19) |
| T5 | Model client interface and OpenAI compatible client | R14, R15, R27 | [#22](https://github.com/hawkxdev/reply-assistant/issues/22) |
| T6 | Service function with validation, checks and one retry; fake model client for its tests | R13 | [#25](https://github.com/hawkxdev/reply-assistant/issues/25) |
| T7 | `POST /api/suggest` with error mapping | R18, R21 | |
| T8 | Web page | R20, R22 to R26 | |
| T9 | Fallback to the secondary provider | R16 | |
| T10 | CRM event adapter and webhook endpoint | R19 | |
| T11 | Live evaluation workflow started by hand | Acceptance 2 | |

T1 to T8 produce a service that can be shown. T9 to T11 follow.
