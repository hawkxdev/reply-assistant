"""Acceptance for issue 36."""

from pathlib import Path

import pytest

from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.prompt import build_messages

pytestmark = pytest.mark.xfail(strict=True, reason='issue 36 is not implemented')

# === Data ===

KB_FILE = Path(__file__).parents[2] / 'kb' / 'example-en.yaml'
CUSTOMER = 'Does the powder cure allergies?'
RULES = [
    (
        'customer_reply is the text for the customer, in the language of the '
        'knowledge base. Follow reply_rules and state only facts from the '
        'knowledge base.'
    ),
    (
        'Never write a stem from forbidden_claims in customer_reply or '
        'upsell_hint, in any form, not even in a negation and not when repeating '
        'the words of the customer. Say what the product is instead.'
    ),
    (
        'upsell_product_id is the id of one product that suits the customer, '
        'preferably from goes_with of the product in question, or null when '
        'nothing fits. upsell_hint tells the manager what to offer and why.'
    ),
    (
        'kb_match is found when the knowledge base answers the question, partial '
        'when it answers part of it, none when it does not.'
    ),
]

# === Helpers ===


async def system_lines() -> list[str]:
    """Lines of the system message."""
    kb = await load_knowledge_base(KB_FILE)
    return build_messages(kb, CUSTOMER)[0]['content'].splitlines()


# === Rules ===


@pytest.mark.parametrize('rule', RULES, ids=['reply', 'stems', 'upsell', 'match'])
async def test_system_states_the_rule_after_the_knowledge_base(rule: str) -> None:
    lines = await system_lines()
    end = lines.index('</knowledge_base>')

    assert rule in lines[end + 1 :]
