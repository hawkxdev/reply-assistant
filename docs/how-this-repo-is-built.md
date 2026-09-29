# How this repository is built

Code in this repository is written and reviewed by agents that run on GitHub. A person writes the specification, starts each agent, and merges. This document states who does what and what an agent cannot do.

## The loop

| Step | Actor | Started by | Result |
|---|---|---|---|
| Specification | Person | | `specs/001-reply-and-upsell` |
| Issue | Person | Issue template | A contract with acceptance criteria |
| Acceptance test | Person | | A test in `tests/acceptance`, marked `xfail` until the issue is done |
| Implementation | Author agent | The owner comments `/oc` on the issue | A branch and a pull request labelled `agent-authored` |
| Checks | GitHub Actions | The pull request | Lint, format, types, tests with coverage, title format, dependency review |
| Review | Reviewer agent | The owner comments `@codex review` | Review comments |
| Merge | Person | | A squash commit on `main` |

## Agents

| Role | Agent | Model vendor | Where it runs | Credential in this repository |
|---|---|---|---|---|
| Author | OpenCode | Z.AI | A workflow in this repository | One key, in a protected environment |
| Reviewer | Codex | OpenAI | The vendor's cloud, through its GitHub App | None |

The author and the reviewer come from different vendors on purpose: a model is a weak judge of its own work.

Both agents read [`AGENTS.md`](../AGENTS.md). The reviewer follows its section **Code Review Rules**.

## Trust model

An agent is a program with a shell that follows text. In a public repository anyone can write text into an issue or a comment. The rules below assume that such text is hostile.

**Who can start an agent.** Only the repository owner. The workflow checks the author of the comment before anything else runs, and the agent's own checks come after that, not instead of it.

**Who can write text the agent reads.** Interaction in this repository is limited to collaborators, and the owner is the only collaborator. An issue that is handed to the author agent contains text written by the owner.

**Which secrets exist.**

| Secret | Holder | Used by |
|---|---|---|
| Key of the author agent's model | Environment `author-agent` | The author workflow only |

The key of the service's own model provider is not stored here yet. It arrives together with the live evaluation workflow, in its own protected environment, and that workflow is started by hand.

No secret is available to the whole repository. The checks that run on every pull request need no secret: tests use a fake model client.

**What one job may combine.** A job holds at most two of three: untrusted text, secrets, outbound network access. The author job holds a secret and has network access, so the text it reads must come from the owner.

**What an agent cannot change unreviewed.** Workflows, code owners, instruction files, skills, specifications, decision records and acceptance tests belong to the owner in [`CODEOWNERS`](../.github/CODEOWNERS). The ruleset of `main` requires a pull request and green checks.

**What pull requests from forks get.** No secrets. The author agent and the agent review do not run on them. The checks do.

**What is pinned.** Every action is pinned by commit hash. The author action downloads its agent at run time, which a pinned action cannot prevent; this is why its job holds nothing beyond its own model key.

**What is capped.** Every agent job has a time limit and a concurrency group per issue.

## What stays with the person

- Writing the specification, the issues and the acceptance tests.
- Starting every agent.
- Every merge.
- Every change to workflows, instructions and secrets.
- Approving a run that uses a live model key.

## What this repository does not claim

The agents used here are ready tools driven through a pipeline. The repository shows how to set up, contain and check such a pipeline. It is not an agent framework and contains no agent runtime of its own.

## Known limits

- A green run proves the tests the agent could see. The acceptance tests exist for this reason.
- A review by an agent is advice. It finds some mistakes and misses others.
- The instruction files steer an agent and enforce nothing. Enforcement is in permissions, the ruleset and code owners.
