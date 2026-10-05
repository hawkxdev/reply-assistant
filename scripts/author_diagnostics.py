"""Project safe execution diagnostics."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

MAX_EXPORT_BYTES = 16 * 1024 * 1024
FINISH_REASONS = {'stop', 'length', 'tool-calls', 'content-filter', 'error', 'unknown'}

# === Projection ===


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    """Select non textual observations."""
    messages = data.get('messages')
    if not isinstance(messages, list) or not messages:
        return {'capture': 'unavailable'}
    assistants = [
        item for item in messages if item.get('info', {}).get('role') == 'assistant'
    ]
    users = [item for item in messages if item.get('info', {}).get('role') == 'user']
    if not assistants or not users:
        return {'capture': 'unavailable'}
    original = users[0]['info']['id']
    work = [item for item in assistants if item['info'].get('parentID') == original]
    reason = work[-1]['info'].get('finish') if work else None
    final = assistants[-1]['info'].get('finish')
    states = [
        part.get('state', {}).get('status')
        for item in assistants
        for part in item.get('parts', [])
        if part.get('type') == 'tool'
    ]
    return {
        'capture': 'observed',
        'work_finish': reason if reason in FINISH_REASONS else 'unknown',
        'last_finish': final if final in FINISH_REASONS else 'unknown',
        'assistant_messages': len(assistants),
        'completed_tools': states.count('completed'),
        'failed_tools': states.count('error'),
        'pending_tools': states.count('pending') + states.count('running'),
    }


async def capture(arguments: list[str], root: Path) -> Any:
    """Read bounded private metadata."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in ('PATH', 'HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'LANG')
    }
    process = await asyncio.create_subprocess_exec(
        'opencode',
        *arguments,
        cwd=root,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(20):
            if process.stdout is None:
                raise RuntimeError('Diagnostic pipe unavailable')
            try:
                raw = await process.stdout.readexactly(MAX_EXPORT_BYTES + 1)
            except asyncio.IncompleteReadError as error:
                raw = error.partial
            if len(raw) > MAX_EXPORT_BYTES:
                raise ValueError('Diagnostic payload too large')
            await process.wait()
            if process.returncode:
                raise ValueError('Diagnostic command failed')
            return json.loads(raw) if raw.strip() else []
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def collect(root: Path, started_ms: int) -> dict[str, Any]:
    """Collect one scoped session."""
    try:
        sessions = await capture(
            ['session', 'list', '--format', 'json', '--max-count', '10'], root
        )
        candidates = [
            item
            for item in sessions
            if item.get('created', 0) >= started_ms
            and item.get('directory') == str(root)
        ]
        if len(candidates) != 1:
            return {'capture': 'ambiguous' if candidates else 'unavailable'}
        identifier = candidates[0]['id']
        if not re.fullmatch(r'ses_[a-zA-Z0-9]+', identifier):
            return {'capture': 'invalid'}
        data = await capture(['export', identifier, '--sanitize'], root)
        if data.get('info', {}).get('id') != identifier:
            return {'capture': 'invalid'}
        return summarize(data)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError):
        return {'capture': 'unavailable'}
