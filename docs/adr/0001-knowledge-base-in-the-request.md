# 0001. The knowledge base goes into the request whole

## Context

The knowledge base holds a few dozen products and a page of rules: a few thousand tokens. The models in use accept hundreds of thousands.

## Decision

The whole knowledge base is placed into every model request. There is no retrieval step, no embeddings and no vector store.

## Alternatives

| Alternative | Why not |
|---|---|
| Retrieval over embeddings | Adds a failure mode, a wrong retrieval, and infrastructure, and gives nothing while the knowledge base fits into the request |
| Keyword search over products | The model already reads the whole catalogue; a filter in front of it can only hide a product |

## Consequences

- One moving part fewer. A wrong answer is a prompt or model problem, never a retrieval problem.
- Every request pays for the whole knowledge base in input tokens. Provider side caching of the constant part reduces this where the provider supports it.
- The decision is revisited when the knowledge base stops fitting with a comfortable margin. Retrieval then enters behind the `prompt` module and nothing else changes.
