# Specification 001: reply and upsell hint

## Purpose

A manager answers customers in a chat window of a CRM. For each incoming message the manager needs a draft reply and an idea of what else to offer. The service produces both from a short knowledge base that belongs to the company.

The same service must serve another catalogue or another company after the knowledge base file is replaced, with no code change.

## Users

| User | Need |
|---|---|
| Manager | A reply to send or edit, and a hint visible only to the manager |
| Owner of the knowledge base | To change products and rules by editing one file |
| Integrator | One endpoint to call from a CRM webhook or a low-code scenario |

## Scope

In scope:

- a knowledge base loaded from a file;
- one model call per customer message with structured output;
- checks of the model output by code;
- an HTTP endpoint that returns both blocks;
- a web page that looks like a deal card with a chat and an assistant panel;
- an adapter that accepts the incoming message event of a CRM;
- a second model provider used when the first one fails.

Out of scope:

- a real CRM account and writing back into a CRM;
- retrieval, embeddings and vector stores;
- authentication, deployment, an administration panel, a database;
- storing customer messages.

## Knowledge base

R1. The knowledge base is one YAML file. Its path comes from settings.

R2. The file contains: company name, language of replies, a list of products, reply rules, a list of forbidden claim stems, and an optional disclaimer.

R3. A product has an identifier, a name, a form, a price, a short neutral description, and an optional list of identifiers of products that go well with it.

R4. The file is validated at start. An invalid file stops the service with an error that names the field.

R5. Replacing the file with another valid file changes the behaviour of the service with no code change. The repository contains two example files to prove it.

## Suggestion

R6. The service accepts a customer message as text, from one to 2000 characters.

R7. The service returns a suggestion with these fields:

| Field | Meaning |
|---|---|
| `customer_reply` | Text for the customer in the language of the knowledge base |
| `upsell_product_id` | Identifier of one product from the knowledge base, or null when nothing fits |
| `upsell_hint` | Text for the manager: what to offer and why |
| `kb_match` | `found`, `partial` or `none`: how well the knowledge base covers the question |
| `checks` | The result of each check from R9 to R12 |
| `usage` | Input tokens, output tokens and the provider that answered |

R8. The model receives the whole knowledge base, except the disclaimer that code appends (R11), and the customer message in clearly delimited parts. The customer message is data. The system prompt says so.

## Checks by code

R9. **Product exists.** `upsell_product_id` is null or equals the identifier of a product in the loaded knowledge base. Otherwise the suggestion is rejected.

R10. **No forbidden claim.** Neither `customer_reply` nor `upsell_hint` contains a stem from the forbidden list of the knowledge base, compared without regard to case. Otherwise the suggestion is rejected.

R11. **Disclaimer.** When the knowledge base defines a disclaimer, code appends it to `customer_reply`. The model does not write it.

R12. **Shape.** The model output is validated against the schema. Unknown fields, missing fields and wrong types reject the suggestion.

R13. A rejected suggestion is retried once. A second rejection returns an error with the name of the failed check. A rejected text is never returned as a reply.

## Providers

R14. The model client is an interface with one method that takes messages and a schema and returns text and usage.

R15. The primary provider supports strict structured output by JSON schema. The secondary provider may support only a JSON mode. Both outputs pass the same validation.

R16. The secondary provider is used when the primary one fails with a timeout, a connection error, a rate limit or a server error. The switch is written to the log and shown in `usage`. It is never silent.

R17. Provider keys, base addresses and model names come from settings.

## HTTP

R18. `POST /api/suggest` accepts `{"message": "..."}` and returns the suggestion from R7.

R19. `POST /webhooks/crm/messages` accepts the incoming message event in `application/x-www-form-urlencoded` form with keys of the kind `message[add][0][text]`, answers within the time the CRM allows, and hands the message to the same function as R18. Parsing the event is one function.

R20. `GET /` returns the web page. `GET /health` returns the status and the version.

R21. Errors are returned as JSON with a code and a message. Provider responses are never passed through.

## Web page

R22. The page has three parts: deal and contact fields on the left, the chat in the centre, the assistant panel on the right.

R23. The manager types or pastes the customer message into the chat. The assistant panel shows the reply, the upsell hint, the result of each check, and the token usage.

R24. A button puts the reply into the chat input. Nothing is sent anywhere by the page.

R25. The page states that it is a mock of a dialog window. It carries no trademark of any CRM.

R26. The page is one static HTML file with no build step.

## Quality

R27. Tests run without a network and without a key.

R28. Coverage is at or above the threshold in `pyproject.toml`.

R29. No secret value is stored in the repository.

## Acceptance

The work is accepted when:

1. one command from the README starts the service locally;
2. three messages, one of them asking whether a product cures a condition, each produce both blocks, and the third reply promises no treatment;
3. a test shows that a suggestion naming a product outside the knowledge base is rejected;
4. a test shows that the second example knowledge base works with no code change;
5. `.env.example` lists every setting and contains no value.
