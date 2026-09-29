"""Suggestion schema unit tests."""

from pathlib import Path

from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.suggestion import output_schema

# === Data ===

KB_FILE = Path(__file__).parents[1] / 'kb' / 'example-ru.yaml'

# === Tests ===


async def test_schema_follows_the_loaded_knowledge_base() -> None:
    kb = await load_knowledge_base(KB_FILE)

    schema = output_schema(kb)

    assert schema['properties']['upsell_product_id']['anyOf'][0]['enum'] == [
        'brazil-santos-250',
        'ethiopia-sidamo-250',
        'paper-filters-100',
        'hand-grinder',
    ]
