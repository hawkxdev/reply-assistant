"""Classify bounded review ownership."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

MAX_EXECUTOR_RETURNS = 2


def signals(message: dict[str, Any], issue: int) -> list[dict[str, Any]]:
    """Extract scoped coordination records."""
    result = []
    for raw in re.findall(
        r'<!--\s*task-cycle\s+(\{.*?\})\s*-->', message.get('body') or '', re.DOTALL
    ):
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(value, dict) or value.get('issue') != issue:
            continue
        if not all(
            isinstance(value.get(k), str) and value[k]
            for k in ('role', 'event', 'head')
        ):
            continue
        if 'handoff' in value and not isinstance(value['handoff'], str):
            continue
        result.append(dict(value, source_url=message.get('url')))
    return result


def classify(
    snapshot: dict[str, Any], identity: list[Any], history: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify pull request ownership."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    host, repo, issue = identity
    target = (host.casefold(), repo.casefold())
    participants = history.get(
        '_participants', {'lead': [repo.split('/')[0]], 'reviewer': [], 'executor': []}
    )
    for item in snapshot.get('timelineItems', {}).get('nodes', []):
        pr = (item or {}).get('source') or {}
        url = pr.get('url', '')
        parsed = urlparse(url)
        parts = parsed.path.strip('/').split('/')
        if (
            pr.get('__typename') != 'PullRequest'
            or len(parts) != 4
            or parts[2] != 'pull'
            or not parts[3].isdigit()
            or (parsed.netloc.casefold(), '/'.join(parts[:2]).casefold()) != target
            or int(parts[3]) != pr.get('number')
            or url.casefold() in seen
        ):
            continue
        seen.add(url.casefold())
        history_for_pr = history.setdefault(url, {'failed_heads': []})
        previous = set(history_for_pr['failed_heads'])
        failed: set[str] = set()
        if history_for_pr.get('trusted_participants') == participants:
            failed.update(previous)
        reviews = pr.get('reviews', {}).get('nodes', [])
        comments = pr.get('comments', {}).get('nodes', [])
        records: list[dict[str, Any]] = []
        ordered = sorted(
            reviews + comments,
            key=lambda m: m.get('submittedAt') or m.get('createdAt') or '',
        )
        for message in ordered:
            author = (message.get('author') or {}).get('login')
            for signal in signals(message, issue):
                if author not in participants.get(signal['role'], []):
                    continue
                if (
                    signal.get('role') in ('lead', 'reviewer')
                    and signal.get('event') == 'changes-requested'
                    and signal.get('head')
                ):
                    failed.add(signal['head'])
                records.append(dict(signal, sequence=len(records)))
            if message.get(
                'state'
            ) == 'CHANGES_REQUESTED' and author in participants.get('lead', []):
                head = (message.get('commit') or {}).get('oid')
                if head:
                    failed.add(head)
        unresolved = (
            previous | set(history_for_pr.get('unverified_heads', []))
        ) - failed
        unverified = bool(unresolved)
        history_for_pr['failed_heads'] = sorted(failed)
        history_for_pr['trusted_participants'] = participants
        if unverified:
            history_for_pr['unverified_heads'] = sorted(unresolved)
        else:
            history_for_pr.pop('unverified_heads', None)
        requests = [
            r
            for r in records
            if r.get('role') == 'lead'
            and r.get('event') == 'takeover-requested'
            and r.get('handoff')
            and r.get('head')
        ]
        releases = [
            r
            for r in records
            if r.get('role') == 'executor'
            and r.get('event') == 'executor-released'
            and r.get('handoff')
            and r.get('head')
        ]
        pairs = [
            (q, a)
            for q in requests[-1:]
            for a in releases
            if q['handoff'] == a['handoff']
            and q['head'] == a['head']
            and a['sequence'] > q['sequence']
            and a['source_url'] != q['source_url']
        ]
        head = pr.get('headRefOid')
        accepted = any(
            r.get('role') == 'lead'
            and r.get('event') == 'technically-accepted'
            and r.get('head') == head
            for r in records
        )
        if pr.get('state') in ('CLOSED', 'MERGED'):
            phase = 'CLOSED_RECONCILE'
        elif history_for_pr.get('unverified_heads'):
            phase = 'UNVERIFIED_HISTORY'
        elif accepted:
            phase = 'ACCEPTANCE_REPORTED'
        elif pairs:
            phase = (
                'RELEASE_RECORDED'
                if pairs[-1][1]['head'] == head
                else 'RELEASE_HEAD_CHANGED'
            )
        elif requests:
            phase = 'WAITING_EXECUTOR_RELEASE'
        elif len(failed) > MAX_EXECUTOR_RETURNS:
            phase = 'TAKEOVER_REQUIRED'
        elif len(failed) == MAX_EXECUTOR_RETURNS and head not in failed:
            phase = 'LEAD_FINAL_REVIEW'
        elif len(failed) == MAX_EXECUTOR_RETURNS:
            phase = 'EXECUTOR_FINAL_CORRECTION'
        else:
            phase = 'NORMAL_REVIEW'
        output.append(
            {
                'pr': pr['number'],
                'url': url,
                'head': head,
                'phase': phase,
                'failed_review_heads': sorted(failed),
                'executor_returns_remaining': 0
                if unverified
                else max(0, MAX_EXECUTOR_RETURNS - len(failed)),
                'release_evidence': [
                    {
                        'request': q['source_url'],
                        'release': a['source_url'],
                        'head': a['head'],
                        'handoff': a['handoff'],
                    }
                    for q, a in pairs
                ],
            }
        )
    return output


# === Dispatch admission ===


@dataclass(frozen=True)
class DispatchClaim:
    """One verified execution reservation."""

    event: str
    head: str
    kind: str
    run: int
    status: str
    saved: bool


@dataclass(frozen=True)
class DispatchState:
    """Verified durable task observations."""

    task: int
    pr: int | None
    head: str
    opened: bool
    accepted: bool
    takeover: bool
    reviews: tuple[str, ...]
    claims: tuple[DispatchClaim, ...]


@dataclass(frozen=True)
class DispatchDecision:
    """One bounded admission verdict."""

    allowed: bool
    reason: str
    return_number: int = 0


def dispatch_decision(state: DispatchState, event: str) -> DispatchDecision:
    """Decide before reserving execution."""
    if state.task < 1 or not event or not re.fullmatch(r'[0-9a-f]{40}', state.head):
        raise ValueError('Invalid task identity or commit')
    if not state.opened:
        return DispatchDecision(False, 'CLOSED')
    if state.accepted:
        return DispatchDecision(False, 'ACCEPTED')
    if state.takeover:
        return DispatchDecision(False, 'LEAD_OWNS')
    if any(claim.event == event for claim in state.claims):
        return DispatchDecision(False, 'DUPLICATE_EVENT')
    if any(
        claim.status in ('queued', 'in_progress', 'waiting', 'pending')
        for claim in state.claims
    ):
        return DispatchDecision(False, 'EXECUTOR_BUSY')
    if any(claim.status != 'completed' for claim in state.claims):
        return DispatchDecision(False, 'RECONCILE_REQUIRED')
    if any(not claim.saved for claim in state.claims):
        return DispatchDecision(False, 'WORK_NOT_PRESERVED')
    returned = {claim.head for claim in state.claims if claim.kind == 'correction'}
    if (
        len(returned) >= MAX_EXECUTOR_RETURNS
        or len(set(state.reviews)) > MAX_EXECUTOR_RETURNS
    ):
        return DispatchDecision(False, 'LEAD_COMPLETION')
    if state.pr is None:
        if state.claims:
            return DispatchDecision(False, 'INITIAL_ALREADY_RESERVED')
        return DispatchDecision(True, 'INITIAL')
    if not state.claims:
        return DispatchDecision(False, 'UNTRACKED_EXECUTION')
    if state.head in returned:
        return DispatchDecision(False, 'DUPLICATE_REVIEW')
    if state.head not in state.reviews:
        return DispatchDecision(False, 'REVIEW_REQUIRED')
    return DispatchDecision(True, 'CORRECTION', len(returned) + 1)


@dataclass(frozen=True)
class ReleaseProof:
    """Verified ownership transfer evidence."""

    request_id: str
    release_id: str
    request_head: str
    release_head: str
    ordered: bool
    completed: bool
    saved: bool


def lead_write_allowed(state: DispatchState, proof: ReleaseProof) -> bool:
    """Check before lead writing."""
    return bool(
        state.opened
        and not state.accepted
        and proof.request_id
        and proof.request_id == proof.release_id
        and state.head == proof.request_head == proof.release_head
        and proof.ordered
        and proof.completed
        and proof.saved
        and all(claim.status == 'completed' and claim.saved for claim in state.claims)
    )
