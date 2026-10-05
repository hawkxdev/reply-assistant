"""Exercise actual checkout baselines."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from scripts.author_guard import finish, handoff_check, observe, reconcile, reserve

from tests.test_author_guard import HEAD_A, HEAD_B, SETTINGS, FakeSource, receipt
from tests.test_author_recovery import accept_owner_write

# === Fixtures ===


def stopped_pr() -> FakeSource:
    """Build empty PR execution."""
    source = FakeSource()
    source.context = replace(source.context, recovery_run=1)
    source.responses['user'] = {'id': 1}
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    binding = json.loads(
        messages[0]['body'].split('author-dispatch ')[1].split(' -->')[0]
    )
    binding.update(
        schema=2,
        head=HEAD_B,
        checkout_head=HEAD_A,
        pr=2,
        kind='correction',
        base_refs={'refs/heads/main': HEAD_A},
    )
    messages[0] = receipt('author-dispatch', binding, '2026-01-01T00:01:00Z')
    result = dict(
        binding,
        head=HEAD_A,
        saved=False,
        preserved=True,
        worktree_clean=True,
        other_work=False,
        outcome='no_progress',
    )
    messages[1] = receipt('author-result', result, '2026-01-01T00:02:00Z')
    return source


# === Baseline checks ===


@pytest.mark.parametrize(
    'head', [HEAD_A, HEAD_B], ids=['before-switch', 'after-switch']
)
async def test_empty_pr_execution_uses_observed_and_prepared_baselines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    head: str,
) -> None:
    source = stopped_pr()
    branch = 'main' if head == HEAD_A else 'opencode/issue1-example'
    route = 'repos/owner/repo/git/matching-refs/heads/' + branch.replace('/', '%2F')
    source.responses[route] = [{'ref': 'refs/heads/' + branch, 'object': {'sha': head}}]

    async def git(arguments: list[str], root: Path) -> str:
        """Return unchanged checkout evidence."""
        if arguments[1] == 'rev-parse':
            return head
        if arguments[1] == 'branch':
            return branch
        if arguments[1] == 'for-each-ref':
            return 'refs/heads/main ' + HEAD_A + '\nrefs/heads/' + branch + ' ' + head
        if arguments[1] in ('status', 'rev-list'):
            return ''
        raise AssertionError('Unexpected Git operation')

    monkeypatch.setattr('scripts.author_guard.command', git)
    result = await finish(
        source,
        source.context,
        {
            'schema': 2,
            'head': HEAD_B,
            'checkout_head': HEAD_A,
            'run': 1,
            'task': 1,
            'base_refs': {'refs/heads/main': HEAD_A},
        },
        tmp_path,
    )

    assert result['outcome'] == 'no_progress'
    assert result['preserved'] is True
    assert result['head'] == head


@pytest.mark.parametrize('operation', ['resume', 'lead'])
async def test_precheckout_pr_failure_can_recover_or_transfer(operation: str) -> None:
    source = stopped_pr()

    result = await reconcile(
        source, source.context, SETTINGS, 1, operation, HEAD_B, pr=2
    )
    accept_owner_write(source)

    assert result['resume_head'] == HEAD_B
    if operation == 'resume':
        decision = await reserve(
            source, source.context, SETTINGS, 2, 1, checkout_head=HEAD_A
        )
        assert decision['reason'] == 'RECOVERY'
        assert decision['return_number'] == 1
    else:
        assert await handoff_check(source, source.context, SETTINGS) is True


async def test_result_cannot_replace_the_recorded_checkout_baseline() -> None:
    source = stopped_pr()
    messages = source.responses[
        'repos/owner/repo/issues/1/comments?per_page=100&page=1'
    ]
    result = json.loads(messages[1]['body'].split('author-result ')[1].split(' -->')[0])
    result['checkout_head'] = HEAD_B
    messages[1] = receipt('author-result', result, '2026-01-01T00:02:00Z')

    with pytest.raises(ValueError, match='reservation'):
        await observe(source, source.context, SETTINGS)

    assert source.writes == []
