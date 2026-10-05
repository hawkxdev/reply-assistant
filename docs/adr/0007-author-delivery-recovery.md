# 0007. Recover failed author delivery

## Context

An author run can exit successfully after reading and planning without publishing code. The previous guard correctly refused to start again but offered no recovery path for a verified empty attempt. This decision supplements ADR 0006 without changing merge or deployment authority.

## Decision

The existing guard records four outcomes: `no_progress`, `local_changes`, `remote_commit` and `delivered`. Its finalizer checks the checkout, branch refs, stash, reflog, published branch and PR. It retrieves the original reservation from authenticated issue records, not the local file writable by the author. Any outcome except `delivered` fails the delivery step after recording evidence. A delivered result still requires review and acceptance.

The reservation stores both the reviewed task commit and the actual initial checkout commit. An issue-comment workflow can start on the default branch before OpenCode switches to the PR. An unchanged checkout before that switch and an unchanged PR after it are both no progress, provided the worktree and other-work evidence are clean. Recovery and transfer remain bound to the task commit, not the temporary checkout. Missing or inconsistent checkout evidence is rejected.

The owner may append an `author-resolution` record through the guard. It binds the original checkpoint digest, completed workflow run, task and exact next commit. Original records remain unchanged. Resolutions from other actors, edited records, missing evidence and changed target commits cannot authorize execution.

One technical recovery is available for the latest verified empty execution. This is a task-wide budget in `review_handoff.py`, independent of the two correction returns. Changing models or sessions does not reset either budget. A third rejected review still requires lead completion. An uncertain launch is inspected before any retry; an active executor or unpreserved work stays blocked.

## Operator procedure

Inspect the task using the trusted default-branch version:

```bash
uv run python -m scripts.author_guard inspect --repo OWNER/REPO --task ISSUE
```

Add `--pr PR` when inspecting an existing author PR to include its current review and acceptance state.

For a completed empty execution, verify its checkpoint and current remote commit, then choose one disposition:

```bash
uv run python -m scripts.author_guard reconcile --repo OWNER/REPO --task ISSUE --run RUN --head SHA --operation resume
```

A schema 1 checkpoint additionally requires `--legacy-no-work-audit --evidence https://github.com/OWNER/REPO/actions/runs/RUN`. This records the lead's actual audit of logs, branch state and work disposition; a missing PR alone is insufficient. It does not silently upgrade legacy evidence.

Only after successful reconciliation, comment `/oc recover RUN` on the original issue. For an existing PR, reconcile with `--pr PR` and use that PR for the recovery comment, retaining the current-head task marker required by ADR 0006. A repeated command cannot create another admitted recovery.

If the commit was published but the PR is missing, locate or create the PR at that exact branch and commit, then use `--operation publish --pr PR`. This calls no model. If taking over a verified empty execution instead, use `--operation lead`, followed by `handoff-check --repo OWNER/REPO --task ISSUE`; add `--pr PR` to both commands for a PR execution. That authenticated resolution is the explicit empty-work transfer. For delivered work retain the takeover procedure in ADR 0006. Stop the task observer before lead product writes. Transfer is not acceptance.

## Diagnostics and limits

The reservation records requested model and variant. An unset variant is `provider-default`; actual reasoning effort is not inferred. Optional bounded OpenCode session inspection publishes only finish-reason enums and action counts, separating the first prompt from a later summary. It never uploads session exports or text. Missing or ambiguous diagnostics remain unknown and do not grant authority.

Dirty, abandoned or unpublished work blocks recovery. The finalizer does not upload a runner directory or automatically publish uninspected files. A hard cancellation can prevent finalization, and an expired runner can lose unsaved work; these cases need explicit investigation and may remain unrecoverable. Receipts are operational checks, not a sandbox against a compromised owner or GitHub App.

This guard controls the repository author route. Direct OpenCode launches, nested model calls and provider-managed Codex reviews remain outside it. Synthetic tests verify policy and adapter behavior without a model. A live recovery is verified only after the workflow is adopted and an actual run is observed.
