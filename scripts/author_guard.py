"""Gate cloud author execution."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from scripts.review_handoff import (
    DispatchClaim,
    DispatchState,
    ReleaseProof,
    dispatch_decision,
    lead_write_allowed,
    signals,
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
    if not isinstance(value, dict) or value.get('schema') != 1:
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
    return Context(
        repo,
        owner,
        int(repository['id']),
        repository['default_branch'],
        task,
        pr,
        head,
        str(comment['id']),
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
    for binding in bindings:
        run_id = binding['run']
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
        claims.append(
            DispatchClaim(
                str(binding['event']),
                binding['head'],
                binding['kind'],
                run_id,
                status,
                bool(
                    result
                    and result.get('saved') is True
                    and result.get('worktree_clean') is True
                ),
            )
        )
    if len({claim.run for claim in claims}) != len(claims):
        raise ValueError('Duplicate run reservations')
    opened = issue['state'] == 'open'
    reviews: list[str] = []
    accepted = False
    takeover = False
    if context.pr is not None:
        pull = await source.request(f'{prefix}/pulls/{context.pr}')
        if pull['head']['sha'] != context.head:
            raise ValueError('PR head changed during observation')
        if pull['user']['id'] != executor['id']:
            raise ValueError('PR author is not the selected executor')
        if not any(result.get('pr') == context.pr for result in results.values()):
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
    ), list(results.values())


# === Reservation and result ===


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
    source: Source, context: Context, settings: dict[str, str], run: int, attempt: int
) -> dict[str, Any]:
    """Persist before allowing execution."""
    state, _ = await observe(source, context, settings)
    decision = dispatch_decision(state, context.event)
    output = asdict(decision)
    if not decision.allowed:
        return output
    await verify_run(source, context, run, settings['workflow'])
    value = {
        'schema': 1,
        'task': context.task,
        'pr': context.pr,
        'head': context.head,
        'event': context.event,
        'run': run,
        'attempt': attempt,
        'kind': 'correction' if context.pr else 'initial',
        'return_number': decision.return_number,
    }
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
    await append(source, context, 'author-result', value)
    return value


# === Explicit ownership transfer ===


async def handoff_check(
    source: Source, context: Context, settings: dict[str, str]
) -> bool:
    """Verify before lead writing."""
    state, checkpoints = await observe(source, context, settings)
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
        'phase', choices=['resolve', 'claim', 'finish', 'handoff-check']
    )
    parser.add_argument('--repo')
    parser.add_argument('--task', type=int)
    parser.add_argument('--pr', type=int)
    args = parser.parse_args()
    root = await asyncio.to_thread(
        Path(os.environ.get('GITHUB_WORKSPACE', '.')).resolve
    )
    source = GitHub()
    settings_file = Path(
        os.environ.get('AUTHOR_CYCLE_CONFIG', root / '.github/author-cycle.json')
    )
    settings = json.loads(await asyncio.to_thread(settings_file.read_text))
    if args.phase == 'handoff-check':
        if not args.repo or not args.task or not args.pr:
            parser.error('Handoff check needs repository, task and PR')
        repository = await source.request(f'repos/{args.repo}')
        user = await source.request('user')
        if user['id'] != repository['owner']['id']:
            raise ValueError('Only the owner checks lead write authority')
        pull = await source.request(f'repos/{args.repo}/pulls/{args.pr}')
        context = Context(
            args.repo,
            repository['owner']['id'],
            repository['id'],
            repository['default_branch'],
            args.task,
            args.pr,
            pull['head']['sha'],
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
        data = json.loads(await asyncio.to_thread(saved_file.read_text))
        context = Context(**data['context'])
        result = await finish(source, context, data['reservation'], root)
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


def write_output(path: Path, text: str) -> None:
    """Append bounded workflow outputs."""
    with path.open('a') as stream:
        stream.write(text)


if __name__ == '__main__':
    asyncio.run(main())
