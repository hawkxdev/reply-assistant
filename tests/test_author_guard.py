"""Cloud dispatch admission tests."""

import asyncio
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.author_guard import (
    Context,
    finish,
    handoff_check,
    main,
    observe,
    reserve,
    resolve,
)
from scripts.review_handoff import DispatchClaim, DispatchState, dispatch_decision

# === Synthetic source ===

HEAD_A = 'a' * 40
HEAD_B = 'b' * 40
HEAD_C = 'c' * 40
SETTINGS = {'executor': 'opencode-agent[bot]', 'workflow': 'author.yml'}


def receipt(marker: str, value: dict[str, Any], created: str) -> dict[str, Any]:
    """Construct one immutable receipt."""
    return {
        'body': f'<!-- {marker} {json.dumps(value)} -->',
        'user': {'id': 9, 'login': 'github-actions[bot]', 'type': 'Bot'},
        'created_at': created,
        'updated_at': created,
    }


class FakeSource:
    """Record deterministic source operations."""

    def __init__(self) -> None:
        """Build one synthetic task."""
        self.context = Context('owner/repo', 1, 10, 'main', 1, 2, HEAD_B, '102')
        self.writes: list[dict[str, Any]] = []
        self.fail_write = False
        initial = {
            'schema': 1,
            'task': 1,
            'pr': None,
            'head': HEAD_A,
            'event': '100',
            'run': 1,
            'attempt': 1,
            'kind': 'initial',
        }
        run = {
            'repository': {'id': 10},
            'path': 'author.yml',
            'event': 'issue_comment',
            'head_branch': 'main',
            'actor': {'id': 1},
            'triggering_actor': {'id': 1},
            'status': 'completed',
            'run_attempt': 1,
            'created_at': '2026-01-01T00:00:00Z',
            'updated_at': '2026-01-01T00:03:00Z',
        }
        self.responses: dict[str, Any] = {
            'users/opencode-agent%5Bbot%5D': {'id': 3, 'type': 'Bot'},
            'users/github-actions%5Bbot%5D': {'id': 9, 'type': 'Bot'},
            'repos/owner/repo': {
                'id': 10,
                'owner': {'id': 1},
                'default_branch': 'main',
            },
            'repos/owner/repo/issues/1': {'state': 'open'},
            'repos/owner/repo/issues/1/comments?per_page=100&page=1': [
                receipt('author-dispatch', initial, '2026-01-01T00:01:00Z'),
                receipt(
                    'author-result',
                    dict(initial, pr=2, head=HEAD_B, saved=True, worktree_clean=True),
                    '2026-01-01T00:02:00Z',
                ),
            ],
            'repos/owner/repo/actions/runs/1': run,
            'repos/owner/repo/actions/runs/2': dict(
                run, status='in_progress', created_at='2026-01-01T00:04:00Z'
            ),
            'repos/owner/repo/actions/runs/3': dict(
                run, status='in_progress', created_at='2026-01-01T00:04:00Z'
            ),
            'repos/owner/repo/pulls/2': {
                'state': 'open',
                'user': {'id': 3, 'login': 'opencode-agent[bot]'},
                'number': 2,
                'head': {
                    'sha': HEAD_B,
                    'ref': 'opencode/issue1-example',
                    'repo': {'id': 10},
                },
            },
            'repos/owner/repo/pulls/2/reviews?per_page=100&page=1': [
                {'user': {'id': 1}, 'state': 'CHANGES_REQUESTED', 'commit_id': HEAD_B},
            ],
            'repos/owner/repo/issues/2/comments?per_page=100&page=1': [],
            'repos/owner/repo/issues/1/timeline?per_page=100&page=1': [],
        }
        self.responses.update(
            {
                key + '/attempts/1': value
                for key, value in list(self.responses.items())
                if '/actions/runs/' in key
            }
        )

    async def request(self, route: str, body: dict[str, Any] | None = None) -> Any:
        """Enforce recorded request routes."""
        if body is not None:
            if self.fail_write:
                raise RuntimeError('Synthetic uncertain write')
            self.writes.append(copy.deepcopy(body))
            marker, raw = body['body'].split('<!-- ', 1)[1].split(' ', 1)
            value = json.loads(raw.split(' -->')[0])
            self.responses[
                'repos/owner/repo/issues/1/comments?per_page=100&page=1'
            ].append(receipt(marker, value, '2026-01-01T00:05:00Z'))
            return {'id': 200}
        return copy.deepcopy(self.responses[route])


def policy_state() -> DispatchState:
    """Construct verified policy inputs."""
    return DispatchState(
        1,
        2,
        HEAD_B,
        True,
        False,
        False,
        (HEAD_B,),
        (DispatchClaim('100', HEAD_A, 'initial', 1, 'completed', True),),
    )


def owner_signal(event: str, head: str = HEAD_B) -> dict[str, Any]:
    """Construct authenticated lead coordination."""
    value = {
        'issue': 1,
        'role': 'lead',
        'event': event,
        'head': head,
        'handoff': 'transfer',
    }
    return {
        'body': f'<!-- task-cycle {json.dumps(value)} -->',
        'user': {'id': 1},
        'created_at': '2026-01-01T00:04:00Z',
        'updated_at': '2026-01-01T00:04:00Z',
    }


# === Policy admission ===


@pytest.mark.parametrize(
    ('change', 'event', 'reason'),
    [
        ({'pr': None, 'claims': (), 'reviews': ()}, 'new', 'INITIAL'),
        ({}, 'new', 'CORRECTION'),
        (
            {
                'claims': (
                    DispatchClaim('r1', HEAD_A, 'correction', 1, 'completed', True),
                ),
                'reviews': (HEAD_B,),
            },
            'new',
            'CORRECTION',
        ),
        (
            {
                'claims': (
                    DispatchClaim('r1', HEAD_A, 'correction', 1, 'completed', True),
                    DispatchClaim('r2', HEAD_C, 'correction', 2, 'completed', True),
                )
            },
            'new',
            'LEAD_COMPLETION',
        ),
        ({}, '100', 'DUPLICATE_EVENT'),
        (
            {
                'claims': (
                    DispatchClaim('r1', HEAD_B, 'correction', 2, 'completed', True),
                )
            },
            'new',
            'DUPLICATE_REVIEW',
        ),
        ({'reviews': (HEAD_A,)}, 'new', 'REVIEW_REQUIRED'),
        (
            {'claims': (DispatchClaim('100', HEAD_A, 'initial', 1, 'unknown', False),)},
            'new',
            'RECONCILE_REQUIRED',
        ),
        (
            {
                'claims': (
                    DispatchClaim('100', HEAD_A, 'initial', 1, 'in_progress', False),
                )
            },
            'new',
            'EXECUTOR_BUSY',
        ),
        (
            {
                'claims': (
                    DispatchClaim('100', HEAD_A, 'initial', 1, 'completed', False),
                )
            },
            'new',
            'WORK_NOT_PRESERVED',
        ),
        ({'accepted': True}, 'new', 'ACCEPTED'),
        ({'takeover': True}, 'new', 'LEAD_OWNS'),
        ({'opened': False}, 'new', 'CLOSED'),
        ({'claims': ()}, 'new', 'UNTRACKED_EXECUTION'),
        ({'pr': None}, 'new', 'INITIAL_ALREADY_RESERVED'),
    ],
    ids=[
        'initial',
        'first',
        'second',
        'third',
        'event',
        'same-head',
        'stale',
        'unknown',
        'busy',
        'unsaved',
        'accepted',
        'takeover',
        'closed',
        'legacy',
        'issue-reset',
    ],
)
def test_admission_reconstructs_bounded_task_state(
    change: dict[str, Any], event: str, reason: str
) -> None:
    result = dispatch_decision(replace(policy_state(), **change), event)

    assert result.reason == reason
    assert result.allowed == (reason in ('INITIAL', 'CORRECTION'))
    if reason == 'CORRECTION':
        assert result.return_number == (2 if 'claims' in change else 1)


# === Cloud evidence ===


async def test_reservation_is_durable_before_another_run_can_start() -> None:
    source = FakeSource()
    result = await reserve(source, source.context, SETTINGS, 2, 1)
    replay = await reserve(source, source.context, SETTINGS, 3, 1)

    assert result['allowed'] is True
    assert replay['reason'] == 'DUPLICATE_EVENT'
    assert len(source.writes) == 1


async def test_reviewer_cannot_authorize_a_correction() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/pulls/2/reviews?per_page=100&page=1'][0]['user'][
        'id'
    ] = 77
    result = await reserve(source, source.context, SETTINGS, 2, 1)

    assert result['reason'] == 'REVIEW_REQUIRED'
    assert source.writes == []


@pytest.mark.parametrize(
    'field',
    [
        'workflow',
        'repository',
        'actor',
        'event',
        'branch',
        'attempt',
        'window',
        'edited',
    ],
)
async def test_forged_workflow_receipt_cannot_change_budget(field: str) -> None:
    source = FakeSource()
    run = source.responses['repos/owner/repo/actions/runs/1']
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    if field == 'workflow':
        run['path'] = 'other.yml'
    elif field == 'repository':
        run['repository']['id'] = 11
    elif field == 'actor':
        run['triggering_actor']['id'] = 77
    elif field == 'event':
        run['event'] = 'workflow_dispatch'
    elif field == 'branch':
        run['head_branch'] = 'untrusted'
    elif field == 'attempt':
        run['run_attempt'] = 2
    elif field == 'window':
        run['created_at'] = '2026-01-01T00:04:00Z'
    else:
        messages[0]['updated_at'] = '2026-01-01T00:02:00Z'
    with pytest.raises(ValueError, match=r'(?i)receipt'):
        await reserve(source, source.context, SETTINGS, 2, 1)

    assert source.writes == []


async def test_unknown_reservation_write_never_returns_permission() -> None:
    source = FakeSource()
    source.fail_write = True
    with pytest.raises(RuntimeError, match='Synthetic uncertain write'):
        await reserve(source, source.context, SETTINGS, 2, 1)

    assert source.writes == []


async def test_completed_run_without_result_requires_reconciliation() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'].pop()
    result = await reserve(source, replace(source.context, pr=None), SETTINGS, 2, 1)

    assert result['reason'] == 'RECONCILE_REQUIRED'
    assert source.writes == []


async def test_third_accepted_version_does_not_invoke_an_executor() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/issues/2/comments?per_page=100&page=1'] = [
        owner_signal('technically-accepted')
    ]
    result = await reserve(source, source.context, SETTINGS, 2, 1)

    assert result['reason'] == 'ACCEPTED'
    assert source.writes == []


async def test_controller_restart_reuses_the_server_reservation() -> None:
    source = FakeSource()
    await reserve(source, source.context, SETTINGS, 2, 1)
    restarted = FakeSource()
    restarted.responses = copy.deepcopy(source.responses)
    result = await reserve(
        restarted, replace(source.context, event='103'), SETTINGS, 3, 1
    )

    assert result['reason'] == 'EXECUTOR_BUSY'
    assert restarted.writes == []


async def test_handoff_is_not_a_write_permit_while_cloud_is_busy() -> None:
    source = FakeSource()
    request = owner_signal('takeover-requested')
    release = dict(
        owner_signal('executor-released'),
        user={'id': 3, 'login': 'opencode-agent[bot]'},
        created_at='2026-01-01T00:05:00Z',
        updated_at='2026-01-01T00:05:00Z',
    )
    marker = {
        'issue': 1,
        'role': 'executor',
        'event': 'executor-released',
        'head': HEAD_B,
        'handoff': 'transfer',
        'run_id': 1,
    }
    release['body'] = f'<!-- task-cycle {json.dumps(marker)} -->'
    source.responses['repos/owner/repo/issues/2/comments?per_page=100&page=1'] = [
        request,
        release,
    ]
    ready = await handoff_check(source, source.context, SETTINGS)
    source.responses['repos/owner/repo/actions/runs/1'] = dict(
        source.responses['repos/owner/repo/actions/runs/1'],
        status='in_progress',
        run_attempt=2,
    )
    busy = await handoff_check(source, source.context, SETTINGS)

    assert ready is True
    assert busy is False


async def test_stale_owner_trigger_is_rejected_before_launch() -> None:
    source = FakeSource()
    comment = owner_signal('changes-requested', HEAD_A)
    comment.update(id=102, body='/oc\n' + comment['body'])
    source.responses['repos/owner/repo/issues/comments/102'] = comment
    event = {
        'repository': {'full_name': 'owner/repo', 'id': 10},
        'comment': {'id': 102, 'user': {'id': 1}},
        'issue': {'number': 2, 'pull_request': {}},
    }
    with pytest.raises(ValueError, match='Review head is stale'):
        await resolve(source, event)

    assert source.writes == []


async def test_arbitrary_bot_text_does_not_restore_a_budget() -> None:
    source = FakeSource()
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    messages[0]['user']['login'] = 'stranger'
    messages[0]['user']['id'] = 77
    with pytest.raises(ValueError, match='trusted reservation'):
        await observe(source, source.context, SETTINGS)

    assert source.writes == []


# === Workflow boundary ===


def test_every_model_step_requires_persisted_admission() -> None:
    workflow = yaml.safe_load(Path('.github/workflows/author-agent.yml').read_text())
    job = workflow['jobs']['author']
    model_steps = [
        step for step in job['steps'] if 'ZHIPU_API_KEY' in step.get('env', {})
    ]

    assert len(model_steps) == 1
    assert model_steps[0]['if'] == "steps.admission.outputs.allowed == 'true'"
    assert (
        job['concurrency']['group'] == 'author-agent-${{ needs.resolve.outputs.task }}'
    )
    assert job['concurrency']['cancel-in-progress'] is False
    assert job['timeout-minutes'] == 30
    assert (
        next(step for step in job['steps'] if step.get('id') == 'admission')['run']
        == 'python3 -m scripts.author_guard claim'
    )


async def test_finished_idle_worker_needs_no_acknowledgement_run() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/issues/2/comments?per_page=100&page=1'] = [
        owner_signal('takeover-requested')
    ]

    assert await handoff_check(source, source.context, SETTINGS) is True
    assert source.writes == []


async def test_checkpoint_at_another_head_cannot_release_current_work() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/issues/2/comments?per_page=100&page=1'] = [
        owner_signal('takeover-requested')
    ]
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    value = json.loads(
        messages[1]['body'].split('author-result ', 1)[1].split(' -->')[0]
    )
    value['head'] = HEAD_C
    messages[1] = receipt('author-result', value, '2026-01-01T00:02:00Z')

    assert await handoff_check(source, source.context, SETTINGS) is False


async def test_rerun_reads_the_original_attempt_before_rejecting_replay() -> None:
    source = FakeSource()
    await reserve(source, source.context, SETTINGS, 2, 1)
    historical = source.responses['repos/owner/repo/actions/runs/2/attempts/1']
    historical.update(status='completed', updated_at='2026-01-01T00:07:00Z')
    source.responses['repos/owner/repo/actions/runs/2'] = dict(
        historical, run_attempt=2, status='in_progress'
    )
    value = {
        'schema': 1,
        'task': 1,
        'pr': 2,
        'head': HEAD_B,
        'event': '102',
        'run': 2,
        'attempt': 1,
        'kind': 'correction',
        'saved': True,
        'worktree_clean': True,
    }
    source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'].append(
        receipt('author-result', value, '2026-01-01T00:06:00Z')
    )
    result = await reserve(source, source.context, SETTINGS, 2, 2)

    assert result['reason'] == 'DUPLICATE_EVENT'
    assert len(source.writes) == 1


async def test_untrusted_cross_reference_cannot_claim_execution() -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'] = []
    source.responses['repos/owner/repo/issues/1/timeline?per_page=100&page=1'] = [
        {
            'event': 'cross-referenced',
            'source': {
                'issue': {
                    'pull_request': {},
                    'user': {'id': 77},
                    'repository_url': 'https://api.github.com/repos/owner/repo',
                }
            },
        }
    ]
    result = await reserve(source, replace(source.context, pr=None), SETTINGS, 2, 1)

    assert result['allowed'] is True
    assert len(source.writes) == 1


@pytest.mark.parametrize(
    ('dirty', 'remote_head', 'saved'),
    [(False, HEAD_B, True), (True, HEAD_B, False), (False, HEAD_C, False)],
    ids=['published', 'uncommitted', 'different-head'],
)
async def test_finalizer_distinguishes_saved_work_from_unpublished_edits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dirty: bool,
    remote_head: str,
    saved: bool,
) -> None:
    source = FakeSource()
    source.responses['repos/owner/repo/pulls/2']['head']['sha'] = remote_head

    async def git_evidence(arguments: list[str], root: Path) -> str:
        """Return recorded checkout evidence."""
        if arguments[1] == 'rev-parse':
            return HEAD_B
        if arguments[1] == 'branch':
            return 'opencode/issue1-example'
        return ' M product.py' if dirty else ''

    monkeypatch.setattr('scripts.author_guard.command', git_evidence)
    value = await finish(source, source.context, {'run': 1, 'task': 1}, tmp_path)

    assert value['saved'] is saved
    assert value['worktree_clean'] is not dirty
    assert len(source.writes) == 1


@pytest.mark.parametrize('write_fails', [False, True], ids=['reserved', 'uncertain'])
async def test_cli_does_not_publish_permission_before_durable_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_fails: bool
) -> None:
    source = FakeSource()
    source.fail_write = write_fails
    comment = owner_signal('changes-requested')
    comment.update(id=102, body='/oc\n' + comment['body'])
    source.responses['repos/owner/repo/issues/comments/102'] = comment
    event = {
        'repository': {'full_name': 'owner/repo', 'id': 10},
        'comment': {'id': 102, 'user': {'id': 1}},
        'issue': {'number': 2, 'pull_request': {}},
    }
    event_file = tmp_path / 'event.json'
    config = tmp_path / 'settings.json'
    output = tmp_path / 'output.txt'
    await asyncio.to_thread(event_file.write_text, json.dumps(event))
    await asyncio.to_thread(config.write_text, json.dumps(SETTINGS))
    monkeypatch.setenv('GITHUB_EVENT_PATH', str(event_file))
    monkeypatch.setenv('AUTHOR_CYCLE_CONFIG', str(config))
    monkeypatch.setenv('GITHUB_WORKSPACE', str(tmp_path))
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path))
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setenv('GITHUB_RUN_ID', '2')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setattr('scripts.author_guard.GitHub', lambda: source)

    async def branch_evidence(root: Path) -> dict[str, str]:
        """Return original checkout refs."""
        return {'refs/heads/main': HEAD_A}

    monkeypatch.setattr('scripts.author_guard.local_refs', branch_evidence)
    monkeypatch.setattr(sys, 'argv', ['author_guard', 'claim'])
    if write_fails:
        with pytest.raises(RuntimeError, match='Synthetic uncertain write'):
            await main()
        assert not await asyncio.to_thread(output.exists)
    else:
        await main()
        assert 'allowed=true' in await asyncio.to_thread(output.read_text)
        assert len(source.writes) == 1
        assert await asyncio.to_thread((tmp_path / 'author-dispatch.json').exists)


def test_confirmed_reviews_keep_budget_when_a_reservation_disappears() -> None:
    state = replace(policy_state(), reviews=(HEAD_A, HEAD_B, HEAD_C))
    result = dispatch_decision(state, 'after-restart')

    assert result.allowed is False
    assert result.reason == 'LEAD_COMPLETION'
