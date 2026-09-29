# 0003. Agents write and review, a person merges

Amended by [0004](0004-lead-agent.md): a lead agent that acts for the owner writes the acceptance tests and merges.

## Context

The repository is public. An agent that runs here reads text and holds a credential. Public repositories are probed by automated attackers, and agent actions have had vulnerabilities that leaked secrets through issue text.

## Decision

- The author agent runs in a workflow of this repository and is started only by a comment of the owner.
- The reviewer agent belongs to a different vendor and runs in that vendor's cloud. Its verdict is advice.
- A person merges every pull request.
- Interaction in the repository is limited to collaborators.
- The author job holds one secret, the key of its own model, in a protected environment.
- Pipeline files, instruction files, specifications and acceptance tests belong to the owner in `CODEOWNERS`.
- Acceptance tests are written by the owner before the task is handed over.

## Alternatives

| Alternative | Why not |
|---|---|
| Automatic merge after green checks | A green run proves only the tests the agent could see |
| The same vendor as author and reviewer | A model is a weak judge of its own work |
| A repository wide secret | Every job, including one that reads foreign text, would hold it |
| Letting anyone with an issue start the agent | Issue text is an instruction to a program with a shell |

## Consequences

- Nothing happens without the owner. The pipeline is assisted, not autonomous, and says so.
- Outside contributors get checks and no agent.
- The author action installs its agent at run time, so its code cannot be pinned by pinning the action. The job is given nothing worth stealing beyond its own key.
- The description of the loop and its limits is in [How this repository is built](../how-this-repo-is-built.md).
