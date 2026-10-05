"""Exercise authenticated execution recovery."""

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from scripts.author_guard import (
    finish,
    handoff_check,
    main,
    observe,
    reconcile,
    reserve,
    trusted_reservation,
)

from tests.test_author_guard import HEAD_A, HEAD_B, SETTINGS, FakeSource, receipt

# === Source fixtures ===


def empty_source() -> FakeSource:
    """Build stopped empty execution."""
    source = FakeSource()
    source.context = replace(source.context, pr=None, head=HEAD_A, recovery_run=1)
    comments = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    result = json.loads(comments[1]['body'].split('author-result ')[1].split(' -->')[0])
    result.update(head=HEAD_A, pr=None, saved=False, worktree_clean=True)
    comments[1] = receipt('author-result', result, '2026-01-01T00:02:00Z')
    source.responses['user'] = {'id': 1}
    source.responses['repos/owner/repo/git/ref/heads/main'] = {
        'object': {'sha': HEAD_A}
    }
    return source


def accept_owner_write(source: FakeSource) -> None:
    """Append actual owner receipt."""
    message = {
        'body': source.writes[-1]['body'],
        'user': {'id': 1, 'login': 'owner', 'type': 'User'},
        'created_at': '2026-01-01T00:03:30Z',
        'updated_at': '2026-01-01T00:03:30Z',
    }
    source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'][-1] = (
        message
    )


# === Reconciliation ===


async def test_legacy_empty_run_needs_an_explicit_evidence_attestation() -> None:
    source = empty_source()

    with pytest.raises(ValueError, match='Legacy'):
        await reconcile(source, source.context, SETTINGS, 1, 'resume', HEAD_A)

    assert source.writes == []


async def test_owner_can_reconcile_audited_legacy_without_rewriting_history() -> None:
    source = empty_source()
    before = copy.deepcopy(
        source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1']
    )

    result = await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'resume',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    admission = await reserve(source, source.context, SETTINGS, 2, 1)

    assert result['operation'] == 'resume'
    assert (
        source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'][:2]
        == before
    )
    assert admission['allowed'] is True
    assert admission['reservation']['kind'] == 'recovery'
    assert admission['reservation']['recovery_of'] == 1
    assert admission['return_number'] == 0


@pytest.mark.parametrize('defect', ['outsider', 'edited', 'digest', 'stale', 'early'])
async def test_untrusted_or_stale_resolution_does_not_admit_recovery(
    defect: str,
) -> None:
    source = empty_source()
    await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'resume',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    message = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ][-1]
    if defect == 'outsider':
        message['user']['id'] = 99
    elif defect == 'edited':
        message['updated_at'] = '2026-01-01T00:03:31Z'
    elif defect == 'early':
        message['created_at'] = message['updated_at'] = '2026-01-01T00:01:30Z'
    else:
        value = json.loads(
            message['body'].split('author-resolution ')[1].split(' -->')[0]
        )
        value['result_digest' if defect == 'digest' else 'resume_head'] = HEAD_B
        message['body'] = '<!-- author-resolution ' + json.dumps(value) + ' -->'

    if defect in ('edited', 'digest', 'early'):
        with pytest.raises(ValueError, match=r'edited|stale'):
            await reserve(source, source.context, SETTINGS, 2, 1)
    else:
        result = await reserve(source, source.context, SETTINGS, 2, 1)
        assert result['allowed'] is False


async def test_reconciliation_is_idempotent_after_successful_publication() -> None:
    source = empty_source()
    arguments = (source, source.context, SETTINGS, 1, 'resume', HEAD_A)
    await reconcile(
        *arguments,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    result = await reconcile(
        *arguments,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )

    assert result['changed'] is False
    assert len(source.writes) == 1


async def test_historical_reconciliation_survives_a_new_pr_head() -> None:
    source = empty_source()
    await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'resume',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    state, _ = await observe(
        source, replace(source.context, head=HEAD_B, recovery_run=None), SETTINGS
    )

    assert state.claims[0].reconciled is True
    assert state.claims[0].recovery_head == HEAD_A


async def test_empty_checkpoint_can_transfer_to_lead_without_a_model_call() -> None:
    source = empty_source()
    await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'lead',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)

    assert await handoff_check(source, source.context, SETTINGS) is True
    assert len(source.writes) == 1


@pytest.mark.parametrize('status', ['in_progress', 'unknown'])
async def test_active_or_unknown_execution_cannot_be_reconciled(status: str) -> None:
    source = empty_source()
    if status == 'unknown':
        source.responses['repos/owner/repo/issues/1/comments?per_page=100&page=1'].pop()
    else:
        source.responses['repos/owner/repo/actions/runs/1/attempts/1']['status'] = (
            status
        )

    with pytest.raises(ValueError, match=r'active|unknown'):
        await reconcile(source, source.context, SETTINGS, 1, 'resume', HEAD_A)

    assert source.writes == []


@pytest.mark.parametrize('defect', ['valid', 'event', 'edited', 'duplicate'])
async def test_finalizer_uses_the_authenticated_reservation(defect: str) -> None:
    source = empty_source()
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    value = json.loads(
        messages[0]['body'].split('author-dispatch ')[1].split(' -->')[0]
    )
    value.update(schema=2, base_refs={'refs/heads/main': HEAD_A})
    if defect == 'event':
        value['event'] = '999'
    messages[0] = receipt('author-dispatch', value, '2026-01-01T00:01:00Z')
    if defect == 'edited':
        messages[0]['updated_at'] = '2026-01-01T00:01:01Z'
    if defect == 'duplicate':
        messages.append(copy.deepcopy(messages[0]))

    if defect != 'valid':
        with pytest.raises(ValueError, match=r'binding|edited|exactly'):
            await trusted_reservation(source, 'owner/repo', 1, '100', 1, 1, SETTINGS)
    else:
        context, actual = await trusted_reservation(
            source, 'owner/repo', 1, '100', 1, 1, SETTINGS
        )
        assert context.head == HEAD_A
        assert actual == value


@pytest.mark.parametrize(
    ('head', 'remote', 'dirty', 'orphan', 'outcome'),
    [
        (HEAD_A, None, False, False, 'no_progress'),
        (HEAD_B, HEAD_B, False, False, 'remote_commit'),
        (HEAD_B, None, False, False, 'local_changes'),
        (HEAD_A, None, True, False, 'local_changes'),
        (HEAD_A, None, False, True, 'local_changes'),
    ],
)
async def test_finalizer_records_delivery_and_abandoned_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    head: str,
    remote: str | None,
    dirty: bool,
    orphan: bool,
    outcome: str,
) -> None:
    source = empty_source()
    source.responses['repos/owner/repo/pulls?state=open&head=owner%3Awork'] = []
    source.responses['repos/owner/repo/git/matching-refs/heads/work'] = (
        [{'ref': 'refs/heads/work', 'object': {'sha': remote}}] if remote else []
    )

    async def git(arguments: list[str], root: Path) -> str:
        """Return observable checkout state."""
        if arguments[1] == 'rev-parse':
            return head
        if arguments[1] == 'branch':
            return 'work'
        if arguments[1] == 'status':
            return ' M product.py' if dirty else ''
        if arguments[1] == 'for-each-ref':
            return 'refs/heads/main ' + HEAD_A + '\nrefs/heads/work ' + head
        if arguments[1] == 'rev-list':
            return HEAD_B if orphan else ''
        raise AssertionError('Unexpected checkout operation')

    monkeypatch.setattr('scripts.author_guard.command', git)
    result = await finish(
        source,
        source.context,
        {
            'schema': 2,
            'head': HEAD_A,
            'run': 1,
            'task': 1,
            'base_refs': {'refs/heads/main': HEAD_A},
        },
        tmp_path,
    )

    assert result['outcome'] == outcome
    assert result['preserved'] is (outcome != 'local_changes')
    assert outcome in source.writes[0]['body']


async def test_cli_fails_after_recording_a_missing_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = empty_source()
    event_file = tmp_path / 'event.json'
    event_file.write_text('{}')
    config = tmp_path / 'settings.json'
    config.write_text(json.dumps(SETTINGS))
    output = tmp_path / 'output'
    for key, value in {
        'GITHUB_WORKSPACE': str(tmp_path),
        'AUTHOR_CYCLE_CONFIG': str(config),
        'GITHUB_EVENT_PATH': str(event_file),
        'RUNNER_TEMP': str(tmp_path),
        'GITHUB_OUTPUT': str(output),
        'GITHUB_REPOSITORY': 'owner/repo',
        'AUTHOR_TASK': '1',
        'AUTHOR_EVENT': '100',
        'GITHUB_RUN_ID': '1',
        'GITHUB_RUN_ATTEMPT': '1',
    }.items():
        monkeypatch.setenv(key, value)

    async def binding(*args: Any) -> tuple[Any, dict[str, Any]]:
        """Return trusted remote binding."""
        return source.context, {}

    async def checkpoint(*args: Any) -> dict[str, Any]:
        """Record synthetic terminal checkpoint."""
        source.writes.append({'outcome': 'no_progress'})
        return {'outcome': 'no_progress', 'preserved': True}

    monkeypatch.setattr('scripts.author_guard.GitHub', lambda: source)
    monkeypatch.setattr('scripts.author_guard.trusted_reservation', binding)
    monkeypatch.setattr('scripts.author_guard.finish', checkpoint)
    monkeypatch.setattr(sys, 'argv', ['author_guard', 'finish'])
    with pytest.raises(SystemExit, match='2'):
        await main()

    assert source.writes == [{'outcome': 'no_progress'}]
    assert 'outcome=no_progress' in output.read_text()


async def test_published_checkpoint_binds_owner_pr_without_regeneration() -> None:
    source = empty_source()
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    checkpoint = json.loads(
        messages[1]['body'].split('author-result ')[1].split(' -->')[0]
    )
    checkpoint.update(
        schema=2,
        head=HEAD_B,
        outcome='remote_commit',
        preserved=True,
        branch='opencode/issue1-example',
        remote_head=HEAD_B,
    )
    messages[1] = receipt('author-result', checkpoint, '2026-01-01T00:02:00Z')
    source.responses['repos/owner/repo/pulls/2']['user']['id'] = 1

    result = await reconcile(
        source, source.context, SETTINGS, 1, 'publish', HEAD_B, pr=2
    )
    accept_owner_write(source)
    context = replace(source.context, pr=2, head=HEAD_B, recovery_run=None)
    state, _ = await observe(source, context, SETTINGS)
    admission = await reserve(source, context, SETTINGS, 2, 1)

    assert result['pr'] == 2
    assert state.claims[0].outcome == 'delivered'
    assert admission['reason'] == 'CORRECTION'
    assert admission['return_number'] == 1


async def test_lead_handoff_uses_the_latest_resolution_only() -> None:
    source = empty_source()
    await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'lead',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    later = copy.deepcopy(messages[-1])
    value = json.loads(later['body'].split('author-resolution ')[1].split(' -->')[0])
    value['resume_head'] = HEAD_B
    later['body'] = '<!-- author-resolution ' + json.dumps(value) + ' -->'
    later['created_at'] = later['updated_at'] = '2026-01-01T00:04:00Z'
    messages.append(later)

    assert await handoff_check(source, source.context, SETTINGS) is False


async def test_empty_handoff_waits_for_a_running_workflow_rerun() -> None:
    source = empty_source()
    await reconcile(
        source,
        source.context,
        SETTINGS,
        1,
        'lead',
        HEAD_A,
        legacy_audit=True,
        evidence='https://github.com/owner/repo/actions/runs/1',
    )
    accept_owner_write(source)
    source.responses['repos/owner/repo/actions/runs/1'] = dict(
        source.responses['repos/owner/repo/actions/runs/1'],
        status='in_progress',
        run_attempt=2,
    )

    assert await handoff_check(source, source.context, SETTINGS) is False


async def test_reconciliation_cannot_ignore_a_newer_running_attempt() -> None:
    source = empty_source()
    source.responses['repos/owner/repo/actions/runs/1'] = dict(
        source.responses['repos/owner/repo/actions/runs/1'],
        status='in_progress',
        run_attempt=2,
    )

    with pytest.raises(ValueError, match='Current workflow attempt'):
        await reconcile(
            source,
            source.context,
            SETTINGS,
            1,
            'lead',
            HEAD_A,
            legacy_audit=True,
            evidence='https://github.com/owner/repo/actions/runs/1',
        )

    assert source.writes == []
