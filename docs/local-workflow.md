# Local development and delivery

Implementation and verification run in the selected local coding harness. GitHub stores issues, branches, PRs and assessed review. Repository Actions execution is disabled, including manual and generated workflows. The existing provider-managed reviewer connection is retained outside Actions; automatic reviews are disabled, and manual review requires a separate owner assignment. A local CI server or self-hosted runner is not part of this workflow.

## Verification

Use Python 3.12 with uv and Node.js for the JavaScript-backed page tests. Dependencies remain pinned by uv.lock. Start from a clean committed checkout, verify the current base, and run:

```bash
bash scripts/check-local.sh --base <base-commit> --title 'chore: describe the change'
```

The default base is origin/main and the default title is the current commit subject. An explicit title must match the PR title. The script performs the six commands in AGENTS.md with UV_LOCKED=1, rejects deleted test files and records the checked commit, resolved base, title, per-command logs and return codes. A failed command stops the run with its actual nonzero status. A dirty tree or a version change during verification is rejected. Use --output-dir with a fresh private directory to retain the receipts; the default creates a separate temporary directory.

When pyproject.toml or uv.lock changes, the entry also reads GitHub's dependency comparison for the exact base and head using the existing authenticated gh CLI. The archived action's default policy is preserved: added runtime vulnerabilities are rejected at any severity; development and unknown scopes are excluded, and an absent scope means runtime. A successful empty array means no dependency changes and is accepted. A failed request or malformed review data is a failure, never a clean result. No runner or model is launched. Both commits must be published for this metadata query: run the six offline commands before publishing the task branch, then complete the local entry before opening its PR. An unavailable dependency comparison is an explicit acceptance blocker. Unchanged dependency manifests need no remote comparison.

Tests use fake model clients and no network or provider key. Live evaluation remains a separate local command from the README, requiring its own paid-call authorization; it is never part of this entry.

Code, tests, dependencies and verification scripts are inputs to the full run. After a change, repeat affected verification. Documentation-only corrections may reuse the existing full run after a complete tracked-file and file-mode comparison proves all other inputs unchanged. Record both commits and the document assessment rather than relabelling an old run as new.

## Review and integration

Keep one PR per issue and the agent-authored label. Local checks are author self-verification, not independent review. Existing reviewer access does not require or authorize a new cloud review. When a review is explicitly assigned, assess its exact commit and confirmed findings; otherwise preserve the current review stop. Do not reopen old finding processing merely to publish this local route.

The main ruleset retains PR, ownership, resolved-thread, linear-history, deletion and force-push protections. Only requirements for the disabled Actions checks are removed. Never imitate them with custom passing statuses. Merge only an accepted version under actual owner authority and verify the resulting tree. Production deployment and release remain separate operations.

The local entry, its archived workflow sources, tests and workflow contract remain owner paths in AGENTS.md and CODEOWNERS. A non-owner contribution cannot weaken the replacement gate through an unprotected script path.

## Local release preparation

There is no frontend build or repository deployment workflow. An authorized operator prepares the accepted product locally and follows the existing private delivery contract. A reproducible offline package can be prepared without copying the working directory:

```bash
git archive --format=tar --output=<private-release.tar> <accepted-commit> .python-version pyproject.toml uv.lock README.md LICENSE src kb
```

Verify the complete member inventory, file modes and hashes against that commit. Exclude local credentials, private context, runtime catalogues and server configuration; they remain with their existing operational owner. The package carries public example catalogues, not production serving files. Before a separately authorized local deployment verify the target, preserve configuration and runtime data, retain a validated backup and rollback, and check the running service afterward. Preparing an archive is not evidence of deployment.

## Archived sources and restoration

The four former workflow files remain unchanged under scripts/archived-workflows with a .disabled suffix. The retired author helpers and infrastructure tests remain recoverable at their historical Git revision; ADR 0008 keeps shared policy outside this outgoing tree. The author archive is historical source, not an executable route in the current checkout.

Restoration requires a new owner decision and a current executable contract. The author workflow cannot be restored merely by copying its YAML: its helpers are intentionally retired. Inspect dependencies and secrets without disclosure, then restore only separately authorized routes and reconcile branch-check requirements. The archive, a manual dispatch command or an old approval does not authorize restoration. Dependency alerts and unrelated security protections are preserved; their native analysis is distinct from repository Actions jobs.
