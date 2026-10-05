"""Gate cloud author execution."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from scripts.author_diagnostics import collect
from scripts.review_handoff import (
    DispatchClaim,
    DispatchState,
    ReleaseProof,
    WorkEvidence,
    dispatch_decision,
    lead_write_allowed,
    signals,
    work_outcome,
)

# === Source access ===


class Source(Protocol):
    """Authenticated repository observation port."""

    async def request(self, route: str, body: dict[str, Any] | None = None) -> Any:
        """Read or append metadata."""
        ...


class GitHub:
    """Bound authenticated API operations."""

    def __init__(self) -> None:
        """Start bounded request accounting."""
        self.started = time.monotonic()
        self.requests = 0

    async def request(self, route: str, body: dict[str, Any] | None = None) -> Any:
        """Execute one authenticated request."""
        self.requests += 1
        if self.requests > 64 or time.monotonic() - self.started > 60:
            raise RuntimeError('GitHub observation budget exhausted')
        arguments = ['gh', 'api', route]
        if body is not None:
            arguments.extend(['--method', 'POST', '--input', '-'])
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        payload = json.dumps(body).encode() if body is not None else None
        stdout, _ = await asyncio.wait_for(process.communicate(payload), timeout=30)
        if process.returncode != 0:
            raise RuntimeError('GitHub request failed; do not retry blindly')
        return json.loads(stdout)


async def pages(source: Source, route: str) -> list[dict[str, Any]]:
    """Read every bounded page."""
    result: list[dict[str, Any]] = []
    for page in range(1, 21):
        separator = '&' if '?' in route else '?'
        data = await source.request(f'{route}{separator}per_page=100&page={page}')
        if not isinstance(data, list):
            raise ValueError('Expected a paginated record list')
        result.extend(data)
        if len(data) < 100:
            return result
    raise RuntimeError('Pagination incomplete; execution blocked')


def record(message: dict[str, Any], marker: str) -> dict[str, Any] | None:
    """Decode one immutable receipt."""
    matches = re.findall(
        rf'<!--\s*{re.escape(marker)}\s+(\{{.*?\}})\s*-->',
        message.get('body') or '',
        re.DOTALL,
    )
    if not matches:
        return None
    if len(matches) != 1 or message.get('created_at') != message.get('updated_at'):
        raise ValueError('Ambiguous or edited execution receipt')
    value = json.loads(matches[0])
    if (
        not isinstance(value, dict)
        or type(value.get('schema')) is not int
        or value.get('schema') not in (1, 2)
    ):
        raise ValueError('Unsupported execution receipt')
    return value


def owner_message(message: dict[str, Any], owner: int) -> bool:
    """Check immutable owner authorship."""
    return bool(
        message.get('user', {}).get('id') == owner
        and message.get('created_at') == message.get('updated_at')
    )


def coordination(message: dict[str, Any], task: int) -> list[dict[str, Any]]:
    """Read scoped lead signals."""
    return signals({'body': message.get('body'), 'url': message.get('html_url')}, task)


# === Stable task binding ===


@dataclass(frozen=True)
class Context:
    """Authenticated launch event binding."""

    repo: str
    owner: int
    repository: int
    branch: str
    task: int
    pr: int | None
    head: str
    event: str
    recovery_run: int | None = None


async def resolve(source: Source, event: dict[str, Any]) -> Context:
    """Authenticate and bind trigger."""
    repo = event['repository']['full_name']
    repository = await source.request(f'repos/{repo}')
    owner = int(repository['owner']['id'])
    comment = await source.request(
        f'repos/{repo}/issues/comments/{int(event["comment"]["id"])}'
    )
    if (
        not owner_message(comment, owner)
        or event['comment']['user']['id'] != owner
        or repository['id'] != event['repository']['id']
        or (comment.get('body') or '').split(maxsplit=1)[0] not in ('/oc', '/opencode')
    ):
        raise ValueError('Only an immutable owner trigger is eligible')
    number = int(event['issue']['number'])
    pr: int | None = None
    if 'pull_request' in event['issue']:
        pr = number
        raw = re.findall(r'<!--\s*task-cycle\s+(\{.*?\})\s*-->', comment['body'])
        markers = [json.loads(value) for value in raw]
        if len(markers) != 1 or markers[0].get('role') != 'lead':
            raise ValueError('PR triggers need one owner task binding')
        task = markers[0].get('issue')
        if type(task) is not int or task < 1:
            raise ValueError('Invalid issue binding')
        pull = await source.request(f'repos/{repo}/pulls/{pr}')
        if pull['head']['repo']['id'] != repository['id']:
            raise ValueError('Fork execution is not eligible')
        head = pull['head']['sha']
        if markers[0].get('head') != head:
            raise ValueError('Review head is stale')
    else:
        task = number
        tip = await source.request(
            f'repos/{repo}/git/ref/heads/{quote(repository["default_branch"], safe="")}'
        )
        head = tip['object']['sha']
    issue = await source.request(f'repos/{repo}/issues/{task}')
    if 'pull_request' in issue:
        raise ValueError('The task binding must name an issue')
    words = comment['body'].split()
    recovery_run = None
    if len(words) > 1 and words[1] == 'recover':
        if len(words) < 3 or not re.fullmatch(r'[1-9][0-9]*', words[2]):
            raise ValueError('Recovery needs the stopped run identifier')
        recovery_run = int(words[2])
    return Context(
        repo,
        owner,
        int(repository['id']),
        repository['default_branch'],
        task,
        pr,
        head,
        str(comment['id']),
        recovery_run,
    )


# === Durable observations ===


async def verify_run(
    source: Source,
    context: Context,
    run_id: int,
    workflow: str,
    attempt: int | None = None,
) -> dict[str, Any]:
    """Verify actual workflow authority."""
    route = f'repos/{context.repo}/actions/runs/{run_id}'
    if attempt is not None:
        route += f'/attempts/{attempt}'
    run = await source.request(route)
    if (
        run['repository']['id'] != context.repository
        or run['path'] != workflow
        or run['event'] != 'issue_comment'
        or run['head_branch'] != context.branch
        or run['actor']['id'] != context.owner
        or run['triggering_actor']['id'] != context.owner
    ):
        raise ValueError('Receipt does not belong to the authorized workflow')
    return dict(run)


async def observe(
    source: Source, context: Context, settings: dict[str, str]
) -> tuple[DispatchState, list[dict[str, Any]]]:
    """Rebuild authoritative durable state."""
    prefix = f'repos/{context.repo}'
    issue = await source.request(f'{prefix}/issues/{context.task}')
    comments = await pages(source, f'{prefix}/issues/{context.task}/comments')
    executor = await source.request(f'users/{quote(settings["executor"], safe="")}')
    writer = await source.request('users/github-actions%5Bbot%5D')
    if executor['type'] != 'Bot' or writer['type'] != 'Bot':
        raise ValueError('Configured workflow participants are not bots')
    claims: list[DispatchClaim] = []
    bindings: list[dict[str, Any]] = []
    results: dict[int, dict[str, Any]] = {}
    runs: dict[int, dict[str, Any]] = {}
    for message in comments:
        user = message.get('user') or {}
        if user.get('id') != writer['id'] or user.get('type') != 'Bot':
            continue
        value = record(message, 'author-dispatch') or record(message, 'author-result')
        if value is None:
            continue
        if value.get('task') != context.task:
            raise ValueError('Execution receipt names another task')
        run_id = value.get('run')
        if type(run_id) is not int or run_id < 1:
            raise ValueError('Execution receipt lacks a run')
        if run_id not in runs:
            attempt = value.get('attempt')
            if type(attempt) is not int or attempt < 1:
                raise ValueError('Execution receipt lacks an attempt')
            runs[run_id] = await verify_run(
                source, context, run_id, settings['workflow'], attempt
            )
        run = runs[run_id]
        if (
            message['created_at'] < run['created_at']
            or (
                run['status'] == 'completed'
                and message['created_at'] > run['updated_at']
            )
            or value.get('attempt') != run['run_attempt']
        ):
            raise ValueError('Receipt is outside its actual run')
        value = dict(value, created_at=message['created_at'])
        if record(message, 'author-result') is not None:
            if run_id in results:
                raise ValueError('Conflicting execution results')
            results[run_id] = value
        else:
            bindings.append(value)
    if set(results) - {binding['run'] for binding in bindings}:
        raise ValueError('Execution result has no trusted reservation')
    resolutions = await read_resolutions(
        source, context, comments, bindings, results, runs
    )
    for binding in bindings:
        run_id = binding['run']
        if binding.get('kind') not in ('initial', 'correction', 'recovery'):
            raise ValueError('Unknown execution reservation kind')
        result = results.get(run_id)
        run = runs[run_id]
        if result is not None and (
            result.get('event') != binding.get('event')
            or result['created_at'] < binding['created_at']
        ):
            raise ValueError('Result does not match its reservation')
        status = run['status']
        if status == 'completed' and result is None:
            status = 'unknown'
        resolution = resolutions.get(run_id)
        outcome = (result or {}).get('outcome', 'legacy')
        preserved = bool(
            result
            and result.get('preserved', result.get('saved')) is True
            and result.get('worktree_clean') is True
        )
        reconciled = False
        if resolution is not None:
            outcome = (
                'delivered' if resolution['operation'] == 'publish' else 'no_progress'
            )
            preserved = True
            reconciled = True
        claims.append(
            DispatchClaim(
                str(binding['event']),
                binding['head'],
                binding['kind'],
                run_id,
                status,
                preserved,
                outcome,
                reconciled,
                resolution['resume_head']
                if resolution and resolution['operation'] == 'resume'
                else None,
            )
        )
    if len({claim.run for claim in claims}) != len(claims):
        raise ValueError('Duplicate run reservations')
    latest = max(bindings, key=lambda item: item['run'], default={})
    if context.recovery_run is not None and context.pr is None and latest.get('pr'):
        raise ValueError('Recover a PR execution through its bound PR')
    opened = issue['state'] == 'open'
    reviews: list[str] = []
    accepted = False
    takeover = any(value['operation'] == 'lead' for value in resolutions.values())
    if context.pr is not None:
        pull = await source.request(f'{prefix}/pulls/{context.pr}')
        if pull['head']['sha'] != context.head:
            raise ValueError('PR head changed during observation')
        recovered_pr = any(
            value.get('pr') == context.pr and value['operation'] == 'publish'
            for value in resolutions.values()
        )
        if pull['user']['id'] != executor['id'] and not (
            recovered_pr and pull['user']['id'] == context.owner
        ):
            raise ValueError('PR author is not the selected executor')
        if not recovered_pr and not any(
            result.get('pr') == context.pr for result in results.values()
        ):
            raise ValueError('PR is not bound to a recorded execution')
        opened = opened and pull['state'] == 'open'
        review_records = await pages(source, f'{prefix}/pulls/{context.pr}/reviews')
        for review in review_records:
            confirmed = review['state'] == 'CHANGES_REQUESTED' or any(
                signal['role'] == 'lead'
                and signal['event'] == 'changes-requested'
                and signal['head'] == review['commit_id']
                for signal in coordination(review, context.task)
            )
            if review['user']['id'] == context.owner and confirmed:
                reviews.append(review['commit_id'])
        discussion = await pages(source, f'{prefix}/issues/{context.pr}/comments')
        for message in discussion:
            if not owner_message(message, context.owner):
                continue
            for signal in coordination(message, context.task):
                if signal['role'] != 'lead' or signal['head'] != context.head:
                    continue
                accepted |= signal['event'] == 'technically-accepted'
                takeover |= signal['event'] == 'takeover-requested'
    else:
        timeline = await pages(source, f'{prefix}/issues/{context.task}/timeline')
        if (
            any(
                item.get('event') == 'cross-referenced'
                and 'pull_request'
                in (linked := item.get('source', {}).get('issue') or {})
                and linked.get('user', {}).get('id') == executor['id']
                and linked.get('repository_url', '')
                .casefold()
                .endswith('/repos/' + context.repo.casefold())
                for item in timeline
            )
            and not claims
        ):
            raise ValueError('Existing PR requires execution reconciliation')
    return DispatchState(
        context.task,
        context.pr,
        context.head,
        opened,
        accepted,
        takeover,
        tuple(reviews),
        tuple(claims),
        context.recovery_run,
    ), list(results.values())


# === Reservation and result ===


def checkpoint_digest(value: dict[str, Any]) -> str:
    """Bind immutable checkpoint facts."""
    data = {key: item for key, item in value.items() if key != 'created_at'}
    raw = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_empty_checkpoint(
    checkpoint: dict[str, Any],
    binding: dict[str, Any],
    resolution: dict[str, Any],
    repo: str,
) -> None:
    """Verify absence of output."""
    if (
        checkpoint.get('head') != binding['head']
        or checkpoint.get('worktree_clean') is not True
    ):
        raise ValueError('Checkpoint does not establish an empty execution')
    if checkpoint.get('schema') == 2:
        if (
            checkpoint.get('outcome') != 'no_progress'
            or checkpoint.get('other_work') is not False
        ):
            raise ValueError('Checkpoint contains work or uncertainty')
    elif (
        resolution.get('legacy_audit') is not True
        or checkpoint.get('pr') is not None
        or resolution.get('evidence')
        != f'https://github.com/{repo}/actions/runs/{binding["run"]}'
    ):
        raise ValueError('Legacy checkpoint requires an explicit run evidence audit')


async def read_resolutions(
    source: Source,
    context: Context,
    comments: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    results: dict[int, dict[str, Any]],
    runs: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Verify append only resolutions."""
    found: dict[int, dict[str, Any]] = {}
    reserved = {item['run']: item for item in bindings}
    for message in sorted(comments, key=lambda item: item['created_at']):
        if message.get('user', {}).get('id') != context.owner:
            continue
        value = record(message, 'author-resolution')
        if value is None:
            continue
        run_id = value.get('run')
        if (
            value.get('schema') != 2
            or value.get('task') != context.task
            or run_id not in results
        ):
            raise ValueError('Resolution lacks its task checkpoint')
        run = runs[run_id]
        checkpoint = results[run_id]
        if (
            run['status'] != 'completed'
            or message['created_at'] <= run['updated_at']
            or value.get('result_digest') != checkpoint_digest(checkpoint)
            or not re.fullmatch(r'[0-9a-f]{40}', str(value.get('resume_head', '')))
        ):
            raise ValueError('Resolution is stale or does not match terminal evidence')
        operation = value.get('operation')
        if operation in ('resume', 'lead'):
            verify_empty_checkpoint(checkpoint, reserved[run_id], value, context.repo)
        elif operation == 'publish':
            pr = value.get('pr')
            if (
                type(pr) is not int
                or pr < 1
                or checkpoint.get('outcome') != 'remote_commit'
            ):
                raise ValueError('Publication resolution lacks preserved work')
            pull = await source.request(f'repos/{context.repo}/pulls/{pr}')
            if (
                pull['head']['repo']['id'] != context.repository
                or pull['head']['ref'] != checkpoint.get('branch')
                or value.get('resume_head') != checkpoint.get('head')
            ):
                raise ValueError('Publication resolution names another branch')
        else:
            raise ValueError('Unknown resolution operation')
        previous = found.get(run_id)
        if previous and previous['operation'] == 'lead' and operation != 'lead':
            raise ValueError('Cannot replace a lead transfer with another operation')
        if previous is None or message['created_at'] > previous['created_at']:
            found[run_id] = dict(value, created_at=message['created_at'])
        elif message['created_at'] == previous['created_at'] and value != {
            key: item for key, item in previous.items() if key != 'created_at'
        }:
            raise ValueError('Conflicting simultaneous resolutions')
    return found


async def reconcile(
    source: Source,
    context: Context,
    settings: dict[str, str],
    run: int,
    operation: str,
    head: str,
    *,
    legacy_audit: bool = False,
    evidence: str = '',
    pr: int | None = None,
) -> dict[str, Any]:
    """Resolve verified terminal outcomes."""
    user = await source.request('user')
    if user['id'] != context.owner:
        raise ValueError('Only the owner reconciles execution')
    state, checkpoints = await observe(
        source,
        replace(context, pr=None if operation == 'publish' else pr, recovery_run=None),
        settings,
    )
    if not state.opened or state.accepted:
        raise ValueError('Closed or accepted tasks cannot resume')
    if not state.claims or max(item.run for item in state.claims) != run:
        raise ValueError('Reconcile only the latest execution')
    if any(item.status != 'completed' for item in state.claims):
        raise ValueError('Execution is active or its outcome is unknown')
    checkpoint = next(item for item in checkpoints if item['run'] == run)
    if checkpoint.get('pr') is not None and pr != checkpoint['pr']:
        raise ValueError('Reconciliation needs the bound PR')
    claim = next(item for item in state.claims if item.run == run)
    value = {
        'schema': 2,
        'task': context.task,
        'run': run,
        'result_digest': checkpoint_digest(checkpoint),
        'operation': operation,
        'resume_head': head,
        'legacy_audit': legacy_audit,
        'evidence': evidence,
    }
    target_pr = pr or checkpoint.get('pr')
    if target_pr is not None:
        pull = await source.request(f'repos/{context.repo}/pulls/{target_pr}')
        if pull['state'] != 'open' or pull['head']['repo']['id'] != context.repository:
            raise ValueError('Recovery requires an open same repository PR')
        live_head = pull['head']['sha']
    else:
        tip = await source.request(
            f'repos/{context.repo}/git/ref/heads/{quote(context.branch, safe="")}'
        )
        live_head = tip['object']['sha']
    if head != live_head:
        raise ValueError('Recovery target changed before reconciliation')
    if operation in ('resume', 'lead'):
        verify_empty_checkpoint(
            checkpoint, {'head': claim.head, 'run': run}, value, context.repo
        )
        if head != checkpoint['head']:
            comparison = await source.request(
                f'repos/{context.repo}/compare/{checkpoint["head"]}...{head}'
            )
            if comparison['status'] not in ('ahead', 'identical'):
                raise ValueError('Recovery base does not preserve the original history')
        if operation == 'resume':
            reconciled = replace(
                claim,
                saved=True,
                outcome='no_progress',
                reconciled=True,
                recovery_head=head,
            )
            proposed = replace(
                state,
                head=head,
                recovery_run=run,
                claims=tuple(
                    reconciled if item.run == run else item for item in state.claims
                ),
            )
            decision = dispatch_decision(proposed, 'reconciliation')
            if not decision.allowed:
                raise ValueError('Recovery denied: ' + decision.reason)
    elif operation == 'publish':
        if (
            target_pr is None
            or checkpoint.get('outcome') != 'remote_commit'
            or checkpoint.get('worktree_clean') is not True
            or checkpoint.get('head') != head
            or pull['head']['ref'] != checkpoint.get('branch')
        ):
            raise ValueError('Publication requires the exact preserved checkpoint')
        executor = await source.request(f'users/{quote(settings["executor"], safe="")}')
        if pull['user']['id'] not in (context.owner, executor['id']):
            raise ValueError('Publication participant is not authorized')
        value['pr'] = target_pr
    else:
        raise ValueError('Unknown reconciliation operation')
    comments = await pages(
        source, f'repos/{context.repo}/issues/{context.task}/comments'
    )
    for message in reversed(comments):
        if (
            owner_message(message, context.owner)
            and record(message, 'author-resolution') == value
        ):
            return dict(value, changed=False)
    await append(source, context, 'author-resolution', value)
    return dict(value, changed=True)


async def append(
    source: Source, context: Context, marker: str, value: dict[str, Any]
) -> None:
    """Append one execution receipt."""
    encoded = json.dumps(value, sort_keys=True)
    body = f'Author execution metadata.\n\n<!-- {marker} {encoded} -->'
    await source.request(
        f'repos/{context.repo}/issues/{context.task}/comments', {'body': body}
    )


async def reserve(
    source: Source,
    context: Context,
    settings: dict[str, str],
    run: int,
    attempt: int,
    *,
    base_refs: dict[str, str] | None = None,
    requested_model: str = 'unspecified',
    requested_variant: str = 'provider-default',
) -> dict[str, Any]:
    """Persist before allowing execution."""
    if not all(
        re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}', item)
        for item in (requested_model, requested_variant)
    ):
        raise ValueError('Invalid model configuration metadata')
    state, _ = await observe(source, context, settings)
    decision = dispatch_decision(state, context.event)
    output = asdict(decision)
    if not decision.allowed:
        return output
    await verify_run(source, context, run, settings['workflow'])
    value: dict[str, Any] = {
        'schema': 2,
        'task': context.task,
        'pr': context.pr,
        'head': context.head,
        'event': context.event,
        'run': run,
        'attempt': attempt,
        'kind': 'recovery'
        if decision.reason == 'RECOVERY'
        else 'correction'
        if context.pr
        else 'initial',
        'return_number': decision.return_number,
        'started_ms': int(time.time() * 1000),
        'requested_model': requested_model,
        'requested_variant': requested_variant,
    }
    if context.recovery_run is not None:
        value['recovery_of'] = context.recovery_run
    if base_refs is not None:
        value['base_refs'] = base_refs
    await append(source, context, 'author-dispatch', value)
    return dict(output, reservation=value)


async def command(arguments: list[str], root: Path) -> str:
    """Read local checkout evidence."""
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode:
        raise RuntimeError('Checkout evidence is unavailable')
    return stdout.decode().strip()


async def local_refs(root: Path) -> dict[str, str]:
    """Capture local branch checkpoints."""
    text = await command(
        [
            'git',
            'for-each-ref',
            '--format=%(refname) %(objectname)',
            'refs/heads',
            'refs/stash',
        ],
        root,
    )
    refs = {}
    for line in text.splitlines():
        name, sha = line.split()
        if (
            not name.startswith('refs/heads/') and name != 'refs/stash'
        ) or not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Invalid branch checkpoint')
        refs[name] = sha
    return refs


async def trusted_reservation(
    source: Source,
    repo: str,
    task: int,
    event: str,
    run_id: int,
    attempt: int,
    settings: dict[str, str],
) -> tuple[Context, dict[str, Any]]:
    """Reload original workflow reservation."""
    repository = await source.request(f'repos/{repo}')
    context = Context(
        repo,
        repository['owner']['id'],
        repository['id'],
        repository['default_branch'],
        task,
        None,
        '',
        event,
    )
    run = await verify_run(source, context, run_id, settings['workflow'], attempt)
    writer = await source.request('users/github-actions%5Bbot%5D')
    comments = await pages(source, f'repos/{repo}/issues/{task}/comments')
    matches = []
    for message in comments:
        if message.get('user', {}).get('id') != writer['id']:
            continue
        value = record(message, 'author-dispatch')
        if value is None or value.get('run') != run_id:
            continue
        if (
            value.get('task') != task
            or value.get('event') != event
            or value.get('attempt') != attempt
            or value.get('schema') != 2
            or message['created_at'] < run['created_at']
            or (
                run['status'] == 'completed'
                and message['created_at'] > run['updated_at']
            )
        ):
            raise ValueError('Finalizer reservation binding changed')
        matches.append(value)
    if len(matches) != 1:
        raise ValueError('Finalizer needs exactly one trusted reservation')
    value = matches[0]
    return replace(context, pr=value['pr'], head=value['head']), value


async def published_head(source: Source, repo: str, branch: str) -> str | None:
    """Read exact published branch."""
    if not branch:
        return None
    refs = await source.request(
        f'repos/{repo}/git/matching-refs/heads/{quote(branch, safe="")}'
    )
    matched = [
        item['object']['sha'] for item in refs if item['ref'] == 'refs/heads/' + branch
    ]
    if len(matched) > 1:
        raise ValueError('Ambiguous published branch')
    return matched[0] if matched else None


async def finish(
    source: Source, context: Context, reservation: dict[str, Any], root: Path
) -> dict[str, Any]:
    """Capture actual work preservation."""
    head = await command(['git', 'rev-parse', 'HEAD'], root)
    branch = await command(['git', 'branch', '--show-current'], root)
    clean = not await command(['git', 'status', '--porcelain'], root)
    pull: dict[str, Any] | None = None
    if context.pr is not None:
        pull = await source.request(f'repos/{context.repo}/pulls/{context.pr}')
    elif branch:
        selected = quote(context.repo.split('/')[0] + ':' + branch, safe='')
        data = await source.request(
            f'repos/{context.repo}/pulls?state=open&head={selected}'
        )
        if len(data) == 1:
            pull = data[0]
    saved = bool(
        clean
        and pull is not None
        and pull['head']['sha'] == head
        and pull['head']['ref'] == branch
        and pull['head']['repo']['id'] == context.repository
    )
    value = dict(
        reservation,
        head=head,
        pr=pull['number'] if pull else context.pr,
        saved=saved,
        worktree_clean=clean,
    )
    if reservation.get('schema') == 2:
        before = reservation.get('base_refs')
        if not isinstance(before, dict):
            raise ValueError('Reservation lacks original branch evidence')
        refs = await local_refs(root)
        other_work = any(
            sha not in (reservation['head'], head, before.get(ref))
            for ref, sha in refs.items()
        ) or any(ref not in refs for ref in before)
        discarded = await command(
            [
                'git',
                'rev-list',
                '--reflog',
                '--all',
                '--not',
                head,
                *set(before.values()),
            ],
            root,
        )
        other_work |= bool(discarded)
        remote = await published_head(source, context.repo, branch)
        pr_head = pull['head']['sha'] if pull and saved else None
        outcome = work_outcome(
            WorkEvidence(reservation['head'], head, clean, other_work, remote, pr_head)
        )
        value.update(
            branch=branch,
            remote_head=remote,
            other_work=other_work,
            outcome=outcome,
            preserved=outcome in ('no_progress', 'remote_commit', 'delivered'),
        )
    if saved and pull is not None:
        messages = await pages(
            source, f'repos/{context.repo}/issues/{pull["number"]}/comments'
        )
        requests = [
            signal
            for message in messages
            if owner_message(message, context.owner)
            for signal in coordination(message, context.task)
            if signal['role'] == 'lead'
            and signal['event'] == 'takeover-requested'
            and signal['head'] == head
            and signal.get('handoff')
        ]
        if requests:
            value['handoff'] = requests[-1]['handoff']
    if type(reservation.get('started_ms')) is int:
        value['diagnostics'] = await collect(root, reservation['started_ms'])
    await append(source, context, 'author-result', value)
    return value


# === Explicit ownership transfer ===


async def handoff_check(
    source: Source, context: Context, settings: dict[str, str]
) -> bool:
    """Verify before lead writing."""
    state, checkpoints = await observe(source, context, settings)
    if context.pr is None:
        if not state.takeover or not state.claims:
            return False
        last = max(state.claims, key=lambda item: item.run)
        checkpoint = next(item for item in checkpoints if item['run'] == last.run)
        comments = await pages(
            source, f'repos/{context.repo}/issues/{context.task}/comments'
        )
        transfers = [
            dict(value, created_at=item['created_at'])
            for item in comments
            if owner_message(item, context.owner)
            if (value := record(item, 'author-resolution')) is not None
            and value.get('run') == last.run
        ]
        latest = max(transfers, key=lambda item: item['created_at'], default={})
        matching = (
            latest.get('operation') == 'lead'
            and latest.get('resume_head') == context.head
        )
        tip = await source.request(
            f'repos/{context.repo}/git/ref/heads/{quote(context.branch, safe="")}'
        )
        proof = ReleaseProof(
            str(last.run),
            str(last.run) if matching else '',
            context.head,
            tip['object']['sha'],
            matching,
            last.status == 'completed',
            last.saved,
        )
        return checkpoint['head'] == last.head and lead_write_allowed(state, proof)
    executor = await source.request(f'users/{quote(settings["executor"], safe="")}')
    messages = await pages(source, f'repos/{context.repo}/issues/{context.pr}/comments')
    requests: list[dict[str, Any]] = []
    releases: list[dict[str, Any]] = []
    for message in messages:
        for signal in coordination(message, context.task):
            if (
                signal['role'] == 'lead'
                and signal['event'] == 'takeover-requested'
                and owner_message(message, context.owner)
            ):
                requests.append(dict(signal, created=message['created_at']))
            if (
                signal['role'] == 'executor'
                and signal['event'] == 'executor-released'
                and message.get('user', {}).get('id') == executor['id']
                and message.get('created_at') == message.get('updated_at')
            ):
                releases.append(dict(signal, created=message['created_at']))
    if not requests or not state.claims:
        return False
    request = max(requests, key=lambda item: item['created'])
    last = max(state.claims, key=lambda item: item.run)
    captured = [value for value in checkpoints if value.get('run') == last.run]
    saved_at_head = bool(
        len(captured) == 1
        and captured[0].get('saved') is True
        and captured[0].get('worktree_clean') is True
    )
    if not saved_at_head:
        return False
    cloud = await verify_run(source, context, last.run, settings['workflow'])
    checkpoint = captured[0]
    idle = cloud['status'] == 'completed' and cloud['updated_at'] <= request['created']
    acknowledged = (
        checkpoint.get('handoff') == request.get('handoff')
        and request['created'] < checkpoint['created_at']
    )
    release = max(releases, key=lambda item: item['created']) if releases else {}
    released = (
        release.get('run_id') == last.run
        and release.get('handoff') == request.get('handoff')
        and release.get('head') == context.head
        and request['created'] < release['created']
    )
    proof = ReleaseProof(
        request.get('handoff', ''),
        request.get('handoff', '') if idle or acknowledged or released else '',
        request['head'],
        checkpoint['head'],
        idle or acknowledged or released,
        last.status == 'completed' and cloud['status'] == 'completed',
        last.saved and saved_at_head,
    )
    return lead_write_allowed(state, proof)


# === Entry point ===


async def main() -> None:
    """Run the selected operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'phase',
        choices=['resolve', 'claim', 'finish', 'handoff-check', 'inspect', 'reconcile'],
    )
    parser.add_argument('--repo')
    parser.add_argument('--task', type=int)
    parser.add_argument('--pr', type=int)
    parser.add_argument('--run', type=int)
    parser.add_argument('--head')
    parser.add_argument('--operation', choices=['resume', 'lead', 'publish'])
    parser.add_argument('--legacy-no-work-audit', action='store_true')
    parser.add_argument('--evidence', default='')
    args = parser.parse_args()
    root = await asyncio.to_thread(
        Path(os.environ.get('GITHUB_WORKSPACE', '.')).resolve
    )
    source = GitHub()
    settings_file = Path(
        os.environ.get('AUTHOR_CYCLE_CONFIG', root / '.github/author-cycle.json')
    )
    settings = json.loads(await asyncio.to_thread(settings_file.read_text))
    if args.phase in ('inspect', 'reconcile'):
        if not args.repo or not args.task:
            parser.error('Observation needs repository and task')
        repository = await source.request(f'repos/{args.repo}')
        default_branch = quote(repository['default_branch'], safe='')
        tip = await source.request(f'repos/{args.repo}/git/ref/heads/{default_branch}')
        head = args.head or tip['object']['sha']
        if args.phase == 'inspect' and args.pr:
            pull = await source.request(f'repos/{args.repo}/pulls/{args.pr}')
            head = args.head or pull['head']['sha']
        context = Context(
            args.repo,
            repository['owner']['id'],
            repository['id'],
            repository['default_branch'],
            args.task,
            args.pr if args.phase == 'inspect' else None,
            head,
            'inspection',
        )
        if args.phase == 'reconcile':
            if not args.run or not args.operation or not args.head:
                parser.error('Reconciliation needs run, operation and exact head')
            result = await reconcile(
                source,
                context,
                settings,
                args.run,
                args.operation,
                args.head,
                legacy_audit=args.legacy_no_work_audit,
                evidence=args.evidence,
                pr=args.pr,
            )
        else:
            state, checkpoints = await observe(source, context, settings)
            last = max(state.claims, key=lambda item: item.run, default=None)
            recovery = dispatch_decision(
                replace(state, recovery_run=last.run if last else None),
                'inspection-recovery',
            )
            result = {
                'task': args.task,
                'claims': [asdict(item) for item in state.claims],
                'checkpoints': checkpoints,
                'admission': asdict(dispatch_decision(state, 'inspection')),
                'recovery': asdict(recovery),
            }
        print(json.dumps(result))
        return
    if args.phase == 'handoff-check':
        if not args.repo or not args.task:
            parser.error('Handoff check needs repository and task')
        repository = await source.request(f'repos/{args.repo}')
        user = await source.request('user')
        if user['id'] != repository['owner']['id']:
            raise ValueError('Only the owner checks lead write authority')
        if args.pr:
            pull = await source.request(f'repos/{args.repo}/pulls/{args.pr}')
            checked_head = pull['head']['sha']
        else:
            default_branch = quote(repository['default_branch'], safe='')
            tip = await source.request(
                f'repos/{args.repo}/git/ref/heads/{default_branch}'
            )
            checked_head = tip['object']['sha']
        context = Context(
            args.repo,
            repository['owner']['id'],
            repository['id'],
            repository['default_branch'],
            args.task,
            args.pr,
            checked_head,
            'handoff-check',
        )
        allowed = await handoff_check(source, context, settings)
        print(json.dumps({'lead_write_allowed': allowed, 'head': context.head}))
        if not allowed:
            raise SystemExit(2)
        return
    event_file = Path(os.environ['GITHUB_EVENT_PATH'])
    event = json.loads(await asyncio.to_thread(event_file.read_text))
    saved_file = Path(os.environ['RUNNER_TEMP']) / 'author-dispatch.json'
    output_file = Path(os.environ['GITHUB_OUTPUT'])
    if args.phase == 'finish':
        context, reservation = await trusted_reservation(
            source,
            os.environ['GITHUB_REPOSITORY'],
            int(os.environ['AUTHOR_TASK']),
            os.environ['AUTHOR_EVENT'],
            int(os.environ['GITHUB_RUN_ID']),
            int(os.environ['GITHUB_RUN_ATTEMPT']),
            settings,
        )
        result = await finish(source, context, reservation, root)
    else:
        context = await resolve(source, event)
        if args.phase == 'resolve':
            result = {'task': context.task}
        else:
            if context.pr is None:
                local_head = await command(['git', 'rev-parse', 'HEAD'], root)
                if local_head != context.head:
                    raise ValueError('Initial base changed before reservation')
            result = await reserve(
                source,
                context,
                settings,
                int(os.environ['GITHUB_RUN_ID']),
                int(os.environ['GITHUB_RUN_ATTEMPT']),
                base_refs=await local_refs(root),
                requested_model=os.environ.get('MODEL') or 'unspecified',
                requested_variant=os.environ.get('VARIANT') or 'provider-default',
            )
            if result.get('allowed'):
                data = {
                    'context': asdict(context),
                    'reservation': result['reservation'],
                }
                await asyncio.to_thread(saved_file.write_text, json.dumps(data))
    rendered = ''.join(
        f'{key}={str(value).lower()}\n'
        for key, value in result.items()
        if isinstance(value, str | bool | int)
    )
    await asyncio.to_thread(write_output, output_file, rendered)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != 'reservation'}
        )
    )
    if args.phase == 'finish' and result.get('outcome') != 'delivered':
        raise SystemExit(2)


def write_output(path: Path, text: str) -> None:
    """Append bounded workflow outputs."""
    with path.open('a') as stream:
        stream.write(text)


if __name__ == '__main__':
    asyncio.run(main())
