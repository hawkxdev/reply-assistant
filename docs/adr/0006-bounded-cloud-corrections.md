# 0006. Bound cloud correction returns

## Context

A job timeout and a concurrency group bound one execution. They do not limit how many times a coordinator returns a PR to the author. Counting comments also overcounts supplements and loses state when a runner or local session ends.

## Decision

The local lead remains the coordinator. The existing owner-only `/oc` and `/opencode` route stays in `author-agent.yml`; its guard calls the shared policy in `scripts/review_handoff.py`. The guard is an admission adapter, not another agent or reviewer.

1. First review: the author fixes confirmed findings.
2. Second review: the author fixes remaining confirmed findings.
3. Third review: the lead accepts a correct result or completes the frozen remainder. There is no third author return. Lead changes use the same checks and are described as self-verification. If completion needs a new scope or decision, report the verified result, blocker and recommendation.

One initial execution and two correction reservations are retained with the issue. Their identity includes task, PR, triggering comment, exact reviewed commit and actual workflow run/attempt. The same event and another comment on an already returned commit cannot launch another author. Model changes and coordinator restarts do not create a new budget. Confirmed owner reviews provide additional durable evidence; no arbitrary comment can reset it.

## Launch procedure

The first execution uses the owner's comment on an open issue. The resolver authenticates the owner against GitHub and resolves a stable task key. The author job serializes issue and PR commands under that key, retains `cancel-in-progress: false` and a 30-minute timeout, and installs the pinned runtime.

Immediately before the model step the guard fetches complete bounded source pages, validates actor identity and immutable workflow receipts against repository, workflow path, owner, actual attempt and timestamps, and evaluates admission. It appends the reservation before publishing `allowed=true`. Failed reads, ambiguous receipts, uncertain writes and incomplete pagination stop execution. A completed run without a preservation receipt must be reconciled; a job timeout is not proof of saved work.

For a correction the lead first submits a formal `CHANGES_REQUESTED` review against the current commit, with the verified findings. The lead then comments on the author PR:

```text
/oc Fix the confirmed findings from the current review.

<!-- task-cycle {"issue":123,"role":"lead","run":"lead-123","event":"changes-requested","head":"<current-full-commit-sha>"} -->
```

Replace both identifiers with the actual open task and reviewed commit. A stale commit is rejected. Raw reviewer advice is not a launch authorization. Initial issue comments cannot reset an existing execution. Legacy author work without verified receipts stops for reconciliation instead of silently receiving a fresh budget.

## Preservation and handoff

The finalizer executes code from the trusted workflow-source commit, not code edited by the author. It records the actual local commit, matching remote PR, worktree cleanliness and whether work is preserved. A successful job with no published work remains unpreserved. A finalizer failure leaves an uncertain reservation.

Before taking over the lead posts a current-head `takeover-requested` record with a unique `handoff` identifier and the exact remaining scope. If the executor is working, finish or checkpoint its current operation. The finalizer acknowledges a matching request in its authenticated checkpoint; an explicit executor release may also name the same identifier, commit and `run_id`. The lead waits for actual cloud-run completion. Changed heads require a corrected request and verification.

An already ended ephemeral worker needs no new model invocation just to acknowledge transfer. The lead verifies the terminal run and saved checkpoint at the current remote head, and binds that evidence to the takeover request. The read-only preflight is:

```bash
uv run python -m scripts.author_guard handoff-check --repo OWNER/REPO --task ISSUE --pr PR
```

It returns the checked commit and refuses permission if identity, chronology, completion or preservation does not match. Handoff does not approve the product. The lead performs one bounded completion stage, applies the same acceptance criteria and checks, and reports any unresolved blocker without restarting the author loop.

## Limits and verification

The guard limits executor invocations through this repository workflow. Duplicate events can still create Actions infrastructure runs, but cannot produce another admitted model execution. OpenCode direct CLI/app routes and nested model calls inside an admitted shell-capable agent are outside this admission hook. Codex provider-managed automatic review also runs outside the workflow; it may produce further advice, but cannot authorize an author run. No provider-wide model-spend or review-count cap is claimed. The active job has no live lead inbox: a transfer is observed by its finalizer, and the lead waits for termination and preservation.

Workflow receipts rely on the trusted base workflow and GitHub metadata, not on marker text alone. They are operational evidence, not a sandbox against a compromised privileged GitHub App or owner credential. Removed or unavailable run evidence requires reconciliation; it never restores a budget automatically.

Synthetic tests exercise admission, replay, same-head supplements, restarts, stale reviews, unknown results, busy workers, authenticated participants and saved-head transfer. They make no model calls and do not prove a live cloud cycle. A paid live cycle remains a separate observation after this workflow reaches the default branch. Merge, branch protection, secrets and deployment authority are unchanged.

Primary platform contracts: [GitHub issue-comment events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issue_comment), [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency), and [OpenCode GitHub integration](https://opencode.ai/docs/github/).
