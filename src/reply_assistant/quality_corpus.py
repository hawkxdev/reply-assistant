"""Loading of quality documents."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from reply_assistant.quality_schema import (
    KNOWN_FIELD_NAMES,
    QualityDocument,
    validate_quality_document,
)

# === Error ===


class QualityInputError(Exception):
    """Invalid quality document input."""

    def __init__(self, code: str, location: str | None = None) -> None:
        """Keep the safe code."""
        message = code if location is None else f'{code} at {location}'
        super().__init__(message)
        self.code = code
        self.location = location


# === Port ===


def read_quality_bytes(path: Path) -> bytes:
    """Read raw document bytes."""
    return path.read_bytes()


# === Decoding ===


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object keys."""
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise QualityInputError('duplicate_key')
        mapping[key] = value
    return mapping


def _reject_constant(name: str) -> NoReturn:
    """Reject one nonfinite constant."""
    raise QualityInputError('nonfinite_number')


def _decode_document(raw: bytes) -> Any:
    """Decode raw document bytes."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise QualityInputError('encoding') from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except JSONDecodeError:
        raise QualityInputError('json_syntax') from None


# === Validation ===


def _safe_location(error: ValidationError) -> str | None:
    """Build a safe location."""
    parts: list[str] = []
    for segment in error.errors()[0]['loc']:
        if isinstance(segment, int):
            parts.append(str(segment))
        else:
            parts.append(segment if segment in KNOWN_FIELD_NAMES else 'extra')
    return '.'.join(parts) if parts else None


def _structure_document(data: Any) -> QualityDocument:
    """Validate the decoded document."""
    if not isinstance(data, dict):
        raise QualityInputError('schema')
    version = data.get('schema_version')
    if isinstance(version, int) and not isinstance(version, bool) and version != 1:
        raise QualityInputError('unsupported_version')
    try:
        return validate_quality_document(data)
    except ValidationError as error:
        raise QualityInputError('schema', _safe_location(error)) from None


# === Loading ===


@dataclass(frozen=True)
class LoadedQualityDocument:
    """One document with digest."""

    document: QualityDocument
    sha256: str


async def load_quality_document(path: Path) -> LoadedQualityDocument:
    """Load one quality document."""
    try:
        raw = await asyncio.to_thread(read_quality_bytes, path)
    except OSError:
        raise QualityInputError('read_error') from None
    digest = hashlib.sha256(raw).hexdigest()
    data = _decode_document(raw)
    document = _structure_document(data)
    return LoadedQualityDocument(document=document, sha256=digest)
