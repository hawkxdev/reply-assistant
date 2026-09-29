# Security

## Reporting a problem

Report a vulnerability through GitHub private vulnerability reporting: the **Security** tab of this repository, **Report a vulnerability**. Do not open a public issue for it.

## What is in scope

- The service code in `src/reply_assistant`.
- The workflows in `.github/workflows` and the way agents are started.

## How agents are contained

Agents in this repository act on text, so text from outside is treated as hostile.

- Only the repository owner can start an agent. A comment from anyone else starts nothing.
- The author agent runs in an environment that holds one secret, the key of its own model, and nothing else.
- Pipeline files, instruction files and acceptance tests belong to the owner in `CODEOWNERS`.
- Pull requests from forks receive no secrets. Agent review does not run on them.
- A person merges every pull request.

The full description is in [How this repository is built](docs/how-this-repo-is-built.md).

## Secrets

No secret value is stored in the repository. `.env.example` lists names only.
