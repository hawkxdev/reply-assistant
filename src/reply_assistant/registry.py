"""Client knowledge base registry."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base

# === Errors ===


class RegistryError(Exception):
    """Invalid registry file."""


# === Reading ===


def _read_mapping(path: Path) -> dict[str, str]:
    """Read one registry file."""
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError as error:
        raise RegistryError(f'cannot read the registry {path}: {error}') from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RegistryError(f'the registry {path} is not valid JSON') from error
    if not isinstance(data, dict) or not all(
        isinstance(entry, str) for entry in data.values()
    ):
        raise RegistryError(f'the registry {path} must map client ids to paths')
    if 'default' not in data:
        raise RegistryError(f'the registry {path} has no default entry')
    mapping: dict[str, str] = data
    return mapping


def _resolve(path: Path, client: str, entry: str) -> Path:
    """Resolve one registry entry."""
    base = path.parent.resolve()
    resolved = (path.parent / entry).resolve()
    if not resolved.is_relative_to(base):
        raise RegistryError(
            f'the entry {client} of the registry {path} is a path traversal: {entry}'
        )
    return resolved


# === Registry ===


@dataclass(frozen=True)
class Registry:
    """Loaded client registry."""

    path: Path
    default_kb: KnowledgeBase

    async def select(self, client_id: str | None) -> KnowledgeBase:
        """Select one client base."""
        mapping = await asyncio.to_thread(_read_mapping, self.path)
        key = client_id if client_id is not None and client_id in mapping else 'default'
        path = _resolve(self.path, key, mapping[key])
        return await load_knowledge_base(path)


async def load_registry(path: Path) -> Registry:
    """Validate every registry entry."""
    mapping = await asyncio.to_thread(_read_mapping, path)
    default = _resolve(path, 'default', mapping['default'])
    default_kb = await load_knowledge_base(default)
    for client, entry in mapping.items():
        if client == 'default':
            continue
        await load_knowledge_base(_resolve(path, client, entry))
    return Registry(path=path, default_kb=default_kb)
