# 0004. A lead agent acts for the owner

## Context

The loop of [0003](0003-agent-pipeline.md) needs the owner at every step: write the issue, write the acceptance test, start the author, read the review, merge. A task takes two pull requests, and the specification has eleven tasks. The owner's part in these steps repeats: the contract follows from the specification, and a merge follows green checks and a review with no open finding.

## Decision

- A lead agent works in the owner's own session, on the owner's machine, under the owner's account.
- It writes issues and acceptance tests from the specification, starts the author agent, reads the review, sets the title and the label, and merges a pull request whose checks are green and whose review threads are closed.
- The owner decides what is built, sets the rules and the authority of every agent, and accepts the finished work.
- The lead agent stops and asks the owner before it acts on any of these: a review finding it disagrees with; a change to instruction files, workflows, permissions or secrets; work outside the specification; the first start of an agent.
- A pull request of the lead agent carries the label `agent-authored`, like a pull request of the author agent.
- The lead, the author and the reviewer come from three different vendors.

## Alternatives

| Alternative | Why not |
|---|---|
| The owner performs every step by hand | The steps repeat and add waiting, not judgement |
| The author agent writes its own acceptance tests | An agent that writes the tests it must pass can make them easy |
| The lead agent runs as a workflow in the repository | It would need a credential that can merge and edit owner paths, stored where the repository can be attacked |

## Consequences

- 0003 says that a person merges every pull request and that the owner writes the acceptance tests. This record replaces those two statements. The rest of 0003 stands.
- GitHub shows the owner's account on every action of the lead agent. The label and the documents are the disclosure.
- The lead agent holds the owner's credential, so permissions do not limit it. The owner's instructions do. The repository stores no credential for it.
- An acceptance test is still written before the author agent sees the task, and by a different agent. The lead agent proves each one against a throwaway implementation and records the result in the pull request.
- The pull requests merged before this record were made the same way.
