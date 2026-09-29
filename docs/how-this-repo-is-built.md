# How this repository is built

Code in this repository is written and reviewed by agents that run on GitHub. A lead agent in the owner's session prepares each task and merges the result. The owner decides what is built, sets the rules and accepts the finished work. This document states who does what and what an agent cannot do.

## The loop

| Step | Actor | Started by | Result |
|---|---|---|---|
| Specification | Owner | | `specs/001-reply-and-upsell` |
| Issue | Lead agent | Issue template | A contract with acceptance criteria |
| Acceptance test | Lead agent | | A test in `tests/acceptance`, marked `xfail` until the issue is done |
| Implementation | Author agent | The lead agent comments `/oc` on the issue | A branch and a pull request labelled `agent-authored` |
| Checks | GitHub Actions | The pull request | Lint, format, types, tests with coverage, conventions of tests and docstrings, title format, dependency review |
| Review | Reviewer agent | The pull request is opened | Review comments |
| Merge | Lead agent | Green checks and closed review threads | A squash commit on `main` |
| Acceptance | Owner | | The finished work is accepted or sent back |

## Agents

| Role | Agent | Model vendor | Where it runs | Credential in this repository |
|---|---|---|---|---|
| Lead | Claude Code | Anthropic | The owner's machine, under the owner's account | None |
| Author | OpenCode | Z.AI | A workflow in this repository | One key, in a protected environment |
| Reviewer | Codex | OpenAI | The vendor's cloud, through its GitHub App | None |

The three agents come from different vendors on purpose: a model is a weak judge of its own work.

The author and the reviewer read [`AGENTS.md`](../AGENTS.md). The reviewer follows its section **Code Review Rules**.

## The lead agent

The lead agent acts for the owner. GitHub shows the owner's account on everything it does, so the label `agent-authored` and this document are the disclosure.

It stops and asks the owner before it acts on any of these:

- a review finding it disagrees with;
- a change to instruction files, workflows, permissions or secrets;
- work outside the specification;
- the first start of an agent.

It proves each acceptance test before the task is handed over: the test fails without the code, passes against a throwaway implementation, and fails again on each defect injected into that implementation. The result is in the pull request that adds the test.

The reasons are in [ADR 0004](adr/0004-lead-agent.md).

## Trust model

An agent is a program with a shell that follows text. In a public repository anyone can write text into an issue or a comment. The rules below assume that such text is hostile.

**Who can start an agent.** Only the account of the repository owner. The workflow checks the author of the comment before anything else runs, and the agent's own checks come after that, not instead of it.

**Who can write text the agent reads.** Interaction in this repository is limited to collaborators, and the owner is the only collaborator. An issue that is handed to the author agent contains text written in the owner's session.

**Which secrets exist.**

| Secret | Holder | Used by |
|---|---|---|
| Key of the author agent's model | Environment `author-agent` | The author workflow only |

The key of the service's own model provider is not stored here yet. It arrives together with the live evaluation workflow, in its own protected environment, and that workflow is started by hand.

No secret is available to the whole repository. The checks that run on every pull request need no secret: tests use a fake model client.

**What one job may combine.** A job holds at most two of three: untrusted text, secrets, outbound network access. The author job holds a secret and has network access, so the text it reads must come from the owner's session.

**What the author and the reviewer cannot change unreviewed.** Workflows, code owners, instruction files, skills, specifications, decision records and acceptance tests belong to the owner in [`CODEOWNERS`](../.github/CODEOWNERS). The ruleset of `main` requires a pull request and green checks.

**What pull requests from forks get.** No secrets. The author agent and the agent review do not run on them. The checks do.

**What is pinned.** Every action is pinned by commit hash. The author action downloads its agent at run time, which a pinned action cannot prevent; this is why its job holds nothing beyond its own model key.

**What is capped.** Every agent job has a time limit and a concurrency group per issue.

## What the author tool decides by itself

The author action names the branch and writes the pull request title, and it does not apply labels. The agent states the correct title in the pull request body. The lead agent sets the title and the label.

## What stays with the owner

- The specification and every decision record.
- The rules and the authority of every agent.
- Every decision the lead agent stops for.
- Accepting the finished work.
- Approving a run that uses a live model key.

## What this repository does not claim

The agents used here are ready tools driven through a pipeline. The repository shows how to set up, contain and check such a pipeline. It is not an agent framework and contains no agent runtime of its own.

## Known limits

- A green run proves the tests the agent could see. The acceptance tests exist for this reason.
- A review by an agent is advice. It finds some mistakes and misses others.
- The instruction files steer an agent and enforce nothing. Enforcement is in permissions, the ruleset and code owners.
- The lead agent holds the owner's credential. Permissions do not limit it; the owner's instructions do.
- A pull request of the lead agent is merged by the lead agent. Its gates are the checks and the advice of the reviewer agent, and the owner reads the result afterwards.
