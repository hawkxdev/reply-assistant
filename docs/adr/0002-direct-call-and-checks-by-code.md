# 0002. One direct model call, structured output, checks by code

## Context

The task is one step: a message and a knowledge base in, two texts out. The reply goes to a customer of a company that sells products whose advertising is restricted by law, so a wrong sentence has a cost.

## Decision

- The service calls the model directly through an OpenAI compatible endpoint. There is no agent framework.
- The model returns structured output by a JSON schema derived from one model class.
- Code validates the output and then checks its content: the suggested product exists in the knowledge base, and no text contains a forbidden claim.
- A disclaimer is appended by code.
- An output that fails is retried once and then becomes an error.

## Alternatives

| Alternative | Why not |
|---|---|
| An agent framework | The task has one step and no tools; a framework adds dependencies and hides the request |
| Trusting the prompt | A prompt lowers the rate of violations and does not remove them |
| Asking the model to write the disclaimer | The model may omit or reword it |

## Consequences

- The schema guarantees the shape. The checks guarantee the two properties that matter. Everything else in the text is the model's judgement and the manager's review.
- The forbidden list lives in the knowledge base file, so another company brings its own.
- A stem list is a blunt instrument: it can reject a harmless sentence. A rejected suggestion costs one retry.
- A framework becomes worth its cost when the task gains several steps or tools. The model client interface is the seam where it would enter.
