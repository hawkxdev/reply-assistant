# 0008. Keep project knowledge with its owner

## Context

The cloud author route is disabled. Its admission adapter imports a duplicated shared coordination implementation from this repository. Publishing that copy makes the project a second owner of general policy. Project roles also repeat general procedures without a dedicated accessible knowledge shelf.

## Decision

The active route is local implementation and verification. Project-authored roles retain service, evaluator, page and owner-boundary details through a public knowledge shelf. Shared methodology and coordination policy remain with the operator's existing local owner and are not distributed in the project tree. No new external integration or copied policy replaces them.

Retire the cloud author workflow, its configuration, `scripts/author_guard.py`, `scripts/author_diagnostics.py` and `scripts/review_handoff.py` from the current public source. The two project adapters and these infrastructure test modules have no current local consumer after retirement. Preserve their exact source through the existing Git history and a compact retirement record, without a new private runtime copy:

- `tests/test_author_guard.py`
- `tests/test_author_checkout.py`
- `tests/test_author_diagnostics.py`
- `tests/test_author_recovery.py`
- `tests/test_author_recovery_policy.py`

The existing local shared policy remains available to its actual consumers outside this project. No project loader or adapter archive is created merely to retain the disabled route. The retired workflow and configuration remain available at their historical Git version; no command or earlier approval restores cloud execution.

These modules exercise cloud admission, checkout evidence, recovery and diagnostic projection. No product module imports them. Every other product and acceptance test, the product source, catalogue, interpreter and dependency metadata retain their original bytes and modes. Retirement is not a green-test workaround, a coverage change or permission to remove product tests.

## Consequences

This decision supersedes the execution route in 0003, 0004, 0006 and 0007; those accepted records remain unchanged as history. Existing reviewer access does not authorize cloud reviews or old finding processing. Repository protection is retained, and acceptance of an organizational version is separate from deployment.

A public clone includes project instructions, feature contracts and the meaningful project shelf. It does not include private context or the local operator's shared policy. A missing private operational dependency is reported for the operation that needs it, rather than silently publishing it. The directory layout stays compatible with the existing product; no mechanical product relocation is part of this decision.
