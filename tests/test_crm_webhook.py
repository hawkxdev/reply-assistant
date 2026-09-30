"""CRM webhook route tests."""

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import load_knowledge_base
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB = Path(__file__).parents[1] / 'kb'
FORM = 'application/x-www-form-urlencoded'
UPPER_FORM = 'Application/X-WWW-Form-Urlencoded; CHARSET=UTF-8'
BODY = b'message%5Badd%5D%5B0%5D%5Btext%5D=Price%3F'
REPLY = json.dumps(
    {
        'customer_reply': 'Yes, we ship the powder to Minsk.',
        'upsell_product_id': None,
        'upsell_hint': 'Nothing to add today.',
        'kb_match': 'found',
    }
)

# === Media type ===


def test_media_type_is_matched_without_case() -> None:
    kb = asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))
    model = FakeModelClient([REPLY])

    with TestClient(create_app(kb=kb, client=model)) as client:
        response = client.post(
            '/webhooks/crm/messages', content=BODY, headers={'content-type': UPPER_FORM}
        )

    assert response.status_code == 202
    assert response.json() == {'accepted': True}
    assert len(model.calls) == 1


# === Body limit ===


def test_body_of_the_exact_limit_is_parsed_not_rejected() -> None:
    kb = asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))

    with TestClient(create_app(kb=kb, client=FakeModelClient([]))) as client:
        response = client.post(
            '/webhooks/crm/messages',
            content=b'x' * 65536,
            headers={'content-type': FORM},
        )

    assert response.status_code == 422
    assert response.json()['code'] == 'invalid_crm_event'
