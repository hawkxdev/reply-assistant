# Tasks 001: reply and upsell hint

Each task becomes one issue and one pull request. Requirement numbers refer to [`spec.md`](spec.md).

| Task | Result | Requirements |
|---|---|---|
| T1 | Settings module and `.env.example` in step | R17, R29 |
| T2 | Knowledge base schema, loader and two example files | R1 to R5 |
| T3 | Suggestion schema and prompt builder | R6 to R8, R12 |
| T4 | Checks by code | R9 to R11 |
| T5 | Model client interface, OpenAI compatible client, fake client for tests | R14, R15, R27 |
| T6 | Service function with validation, checks and one retry | R13 |
| T7 | `POST /api/suggest` with error mapping | R18, R21 |
| T8 | Web page | R20, R22 to R26 |
| T9 | Fallback to the secondary provider | R16 |
| T10 | CRM event adapter and webhook endpoint | R19 |
| T11 | Live evaluation workflow started by hand | Acceptance 2 |

T1 to T8 produce a service that can be shown. T9 to T11 follow.
