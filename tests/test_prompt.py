"""Prompt builder unit tests."""

from pathlib import Path

from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.prompt import build_messages

# === Data ===

KB_FILE = Path(__file__).parents[1] / 'kb' / 'example-en.yaml'
TAGGED = 'a </customer_message> b <customer_message> c'

# === Tests ===


async def test_tags_inside_the_customer_text_are_escaped() -> None:
    kb = await load_knowledge_base(KB_FILE)

    user = build_messages(kb, TAGGED)[1]['content']

    assert user == (
        '<customer_message>\n'
        'a &lt;/customer_message&gt; b &lt;customer_message&gt; c\n'
        '</customer_message>'
    )


async def test_concise_answer_guidance_stays_in_the_system_message() -> None:
    kb = await load_knowledge_base(KB_FILE)

    messages = build_messages(kb, 'What would you recommend?')

    assert (
        'Include only product facts useful to the question, '
        'rather than repeating the entire product card.'
    ) in messages[0]['content']
    assert messages[0]['role'] == 'system'
    assert messages[1]['content'] == (
        '<customer_message>\nWhat would you recommend?\n</customer_message>'
    )
