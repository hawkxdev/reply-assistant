"""Parsing of CRM message events."""

from urllib.parse import parse_qsl

FORM_TEXT_KEY = 'message[add][0][text]'
FORM_TEXT_PREFIX = 'message[add]['
FORM_TEXT_SUFFIX = '[text]'
TEXT_LIMIT = 2000
_HEX_DIGITS = frozenset('0123456789abcdefABCDEF')

# === Failure ===


class CRMEventError(Exception):
    """Rejected incoming CRM event."""

    def __init__(self) -> None:
        """Set the fixed reason."""
        super().__init__('invalid CRM message event')


# === Checks ===


def _valid_percent_escapes(form: str) -> bool:
    """Check every percent escape."""
    index = form.find('%')
    while index != -1:
        escape = form[index + 1 : index + 3]
        if (
            len(escape) < 2
            or escape[0] not in _HEX_DIGITS
            or escape[1] not in _HEX_DIGITS
        ):
            return False
        index = form.find('%', index + 3)
    return True


# === Parsing ===


def parse_crm_event(body: bytes) -> str:
    """Extract the incoming customer text."""
    try:
        form = body.decode('utf-8')
    except UnicodeDecodeError as error:
        raise CRMEventError() from error
    if not _valid_percent_escapes(form):
        raise CRMEventError()
    try:
        pairs = parse_qsl(form, keep_blank_values=True, errors='strict')
    except UnicodeDecodeError as error:
        raise CRMEventError() from error
    text: str | None = None
    for key, value in pairs:
        if key == FORM_TEXT_KEY:
            if text is not None:
                raise CRMEventError()
            text = value
        elif key.startswith(FORM_TEXT_PREFIX) and key.endswith(FORM_TEXT_SUFFIX):
            raise CRMEventError()
    if text is None or not text or len(text) > TEXT_LIMIT:
        raise CRMEventError()
    return text
