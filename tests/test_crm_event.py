"""CRM event parser tests."""

import pytest

from reply_assistant.crm_event import CRMEventError, parse_crm_event


def test_parser_rejects_a_malformed_escape_outside_the_text() -> None:
    body = b'other=bad%ZZ&message[add][0][text]=Hello'

    with pytest.raises(CRMEventError, match='invalid CRM message event'):
        parse_crm_event(body)


def test_parser_ignores_texts_outside_the_add_section() -> None:
    body = b'message[update][0][text]=Old&message[add][0][text]=Fresh'

    assert parse_crm_event(body) == 'Fresh'
