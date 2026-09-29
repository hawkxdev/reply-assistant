# Plan 001: reply and upsell hint

How the specification is built. Requirement numbers refer to [`spec.md`](spec.md).

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `settings` | Reads settings from the environment | |
| `knowledge_base` | Schema of the file, loading, validation | `settings` |
| `suggestion` | Schema of the model output and of the response | |
| `prompt` | Builds the messages for the model from the knowledge base and the customer message | `knowledge_base` |
| `model_client` | Interface of a model client, an implementation for an OpenAI compatible endpoint, a fallback wrapper | `settings` |
| `checks` | The checks R9 to R12 as pure functions | `knowledge_base`, `suggestion` |
| `service` | One function: message in, checked suggestion out, with one retry | all above |
| `crm_event` | Parses the incoming message event into a message | |
| `app` | HTTP routes and error mapping | `service`, `crm_event` |
| `static/index.html` | The web page | `app` |

Each module is understood and tested without reading the others. `service` is the only place that knows the order of steps.

## Data flow

1. A message arrives at `POST /api/suggest`, or an event arrives at the webhook and `crm_event` extracts the message.
2. `service` asks `prompt` for the messages and `suggestion` for the schema.
3. `model_client` calls the primary provider. On a recoverable failure the fallback wrapper calls the secondary one.
4. `service` validates the output and runs `checks`.
5. On rejection `service` retries once, then returns a typed error.
6. `app` maps the result or the error to JSON.

## Decisions

| Decision | Record |
|---|---|
| The knowledge base goes into the request whole | [ADR 0001](../../docs/adr/0001-knowledge-base-in-the-request.md) |
| One direct model call, structured output, checks by code | [ADR 0002](../../docs/adr/0002-direct-call-and-checks-by-code.md) |
| Agents write and review, a person merges | [ADR 0003](../../docs/adr/0003-agent-pipeline.md) |

## Testing

- `checks`, `prompt`, `knowledge_base` and `crm_event` are pure and tested directly.
- `service` is tested with a fake model client that returns prepared outputs, including invalid ones.
- `app` is tested through the HTTP client with the fake model client injected.
- Acceptance tests in `tests/acceptance` are written by the owner before the task is handed to the author agent.
- A live evaluation of a fixed set of messages runs only when started by hand.

## Order

The tasks in [`tasks.md`](tasks.md) are ordered so that each one leaves `main` working and adds one visible capability.
