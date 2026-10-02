"""Finite answer grammar."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal, cast

from reply_assistant.quality_facts import (
    PriceValue,
    VerifiedFactIndex,
    VerifiedProductFacts,
)
from reply_assistant.quality_schema import (
    Answer,
    AssessmentQuestion,
    RequiredAction,
    RequiredClaim,
)

# === Assessment models ===

ClaimKind = Literal[
    'price',
    'form',
    'description',
    'batch_capacity',
    'object_mass',
    'filter_size',
    'relation',
    'stock',
    'delivery',
    'absence_delivery',
    'absence_stock',
    'directive',
    'service',
    'disclaimer',
]
ProtectionReason = Literal['quote', 'negation', 'condition', 'question']
FieldName = Literal['customer_reply', 'upsell_hint']
Stage = Literal['model_output', 'final_suggestion']
PolicyLanguage = Literal['en', 'ru']
Verdict = Literal['confirmed', 'error', 'manual_review']


@dataclass(frozen=True)
class SourcePolicy:
    """Policy strings of one source."""

    disclaimer: str | None = None
    stage: Stage | None = None
    language: PolicyLanguage = 'en'


@dataclass(frozen=True)
class Claim:
    """One construction claim."""

    product_id: str
    kind: ClaimKind
    start: int
    end: int
    expected: str
    found: str
    matches: bool


@dataclass(frozen=True)
class FieldAssessment:
    """One field assessment."""

    protected: bool
    protection_reason: str | None
    claims: tuple[Claim, ...]
    service_fragments: tuple[Claim, ...]
    remainders: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class AnswerAssessment:
    """Aggregated answer verdict."""

    verdict: Verdict
    grounds: tuple[str, ...]
    unresolved: tuple[str, ...]


# === Protection pass N07 ===

_QUOTE_MARKERS = frozenset('"\'`«»“”‘’„‚')
_WORD_APOSTROPHES = "'’"
_NEGATION_MARKERS = (
    'not',
    'no',
    'never',
    'cannot',
    "can't",
    "don't",
    "doesn't",
    "isn't",
    'не',
    'нет',
    'никогда',
    'нельзя',
)
_CONDITION_MARKERS = (
    'if',
    'unless',
    'when',
    'provided',
    'suppose',
    'hypothetical',
    'than',
    'versus',
    'instead',
    'cheaper',
    'more',
    'less',
    'or',
    'если',
    'когда',
    'при',
    'бы',
    'допустим',
    'предположим',
    'чем',
    'вместо',
    'дороже',
    'дешевле',
    'больше',
    'меньше',
    'или',
)
_LETTER = r'[^\W\d_]'
_LETTER_RE = re.compile(_LETTER)
_MARKER_KINDS: tuple[tuple[str, ProtectionReason], ...] = (
    *((marker, 'negation') for marker in _NEGATION_MARKERS),
    *((marker, 'condition') for marker in _CONDITION_MARKERS),
)
_MARKER_RES = {
    marker: re.compile(
        rf'(?<!{_LETTER}){re.escape(marker)}(?!{_LETTER})', re.IGNORECASE
    )
    for marker in (*_NEGATION_MARKERS, *_CONDITION_MARKERS)
}


def _is_letter(char: str) -> bool:
    """Report one letter character."""
    return bool(char) and _LETTER_RE.fullmatch(char) is not None


def _has_quote_marker(text: str) -> bool:
    """Search one quote marker."""
    for position, char in enumerate(text):
        if char in _WORD_APOSTROPHES:
            before = text[position - 1] if position else ''
            after = text[position + 1] if position + 1 < len(text) else ''
            if _is_letter(before) and _is_letter(after):
                continue
        if char in _QUOTE_MARKERS:
            return True
    return False


def _protection_reason(
    text: str, excluded: Sequence[tuple[int, int]] = ()
) -> ProtectionReason | None:
    """Find the protection reason."""
    if _has_quote_marker(text):
        return 'quote'
    scan = _mask_ranges(text, excluded)
    for marker, reason in _MARKER_KINDS:
        if _MARKER_RES[marker].search(scan):
            return reason
    if '?' in scan:
        return 'question'
    return None


def _mask_ranges(text: str, excluded: Sequence[tuple[int, int]]) -> str:
    """Blank the excluded ranges."""
    if not excluded:
        return text
    chars = list(text)
    for start, end in excluded:
        for position in range(max(start, 0), min(end, len(text))):
            chars[position] = ' '
    return ''.join(chars)


# === Statement split N05 ===

_SEPARATORS = '.!;'
_SPACES_RE = re.compile(r'\s+')


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Trim spaces of one span."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _statements(text: str) -> list[tuple[int, int]]:
    """Split field statements."""
    edges = [0]
    for position, char in enumerate(text):
        if char not in _SEPARATORS:
            continue
        if (
            char == '.'
            and 0 < position < len(text) - 1
            and text[position - 1].isdigit()
            and text[position + 1].isdigit()
        ):
            continue
        edges.append(position)
        edges.append(position + 1)
    edges.append(len(text))
    spans: list[tuple[int, int]] = []
    for index in range(0, len(edges), 2):
        start, end = _trim_span(text, edges[index], edges[index + 1])
        if start < end:
            spans.append((start, end))
    return spans


# === Number and unit grammar N02 N03 ===

_SPACE_KINDS = ' \u00a0\u202f'
_NUMBER_RE = re.compile(rf'(?:\d{{1,3}}(?:[{_SPACE_KINDS}]\d{{3}})+|\d+)(?:[.,]\d+)?')
_CURRENCY_RE = re.compile(r'USD|RUB')
_UNIT_PATTERN = r'pieces|sections|штук|отделений|ml|мл|g|г'
_UNITS: dict[str, str] = {
    'g': 'g',
    'г': 'g',
    'ml': 'ml',
    'мл': 'ml',
    'pieces': 'piece',
    'штук': 'piece',
    'sections': 'section',
    'отделений': 'section',
}
_INTEGER_RE = re.compile(r'[1-9]\d*')
_DIGITS_RE = re.compile(r'\d+')
_MASS_ALIASES: dict[str, str] = {'g': 'g', 'г': 'g'}


def _number_at(text: str, position: int) -> tuple[Decimal, int] | None:
    """Match one number."""
    match = _NUMBER_RE.match(text, position)
    if match is None:
        return None
    raw = match.group(0)
    if len(set(raw).intersection(_SPACE_KINDS)) > 1:
        return None
    for space in _SPACE_KINDS:
        raw = raw.replace(space, '')
    return Decimal(raw.replace(',', '.')), match.end()


def _currency_at(text: str, position: int) -> tuple[str, int] | None:
    """Match one currency code."""
    match = _CURRENCY_RE.match(text, position)
    if match is None:
        return None
    if match.end() < len(text) and _is_letter(text[match.end()]):
        return None
    return match.group(0), match.end()


def _price_at(text: str, position: int) -> tuple[Decimal, str, int] | None:
    """Match one price value."""
    number = _number_at(text, position)
    if number is None:
        return None
    value, after = number
    gap = _SPACES_RE.match(text, after)
    if gap is None:
        return None
    currency = _currency_at(text, gap.end())
    if currency is None:
        return None
    return value, currency[0], currency[1]


def _mass_at(
    text: str, position: int, integer: bool
) -> tuple[Decimal, str, int, int] | None:
    """Match one mass value."""
    gap = _spaces_at(text, position)
    if gap is None:
        return None
    if integer:
        match = _INTEGER_RE.match(text, gap)
        if match is None:
            return None
        value, after = Decimal(match.group(0)), match.end()
    else:
        number = _number_at(text, gap)
        if number is None:
            return None
        value, after = number
    unit_gap = _spaces_at(text, after)
    if unit_gap is None:
        return None
    for spelling, unit in _MASS_ALIASES.items():
        unit_end = _word_at(text, unit_gap, spelling)
        if unit_end is not None:
            return value, unit, gap, unit_end
    return None


# === Form profiles F01 to F08 ===

_QUANTITY_PREDICATES: dict[str, str] = {
    'F01': 'package_quantity',
    'F02': 'package_quantity',
    'F03': 'package_quantity',
    'F04': 'form_quantity',
    'F05': 'section_count',
    'F06': 'package_quantity',
    'F07': 'package_quantity',
    'F08': 'batch_capacity',
}
_QUANTITY = r'(?P<quantity>[1-9]\d*)'
_UNIT = rf'(?P<unit>{_UNIT_PATTERN})'
_FORM_CORES: dict[str, tuple[re.Pattern[str], ...]] = {
    'F01': (
        re.compile(rf'(?i:powder)\s*,\s*{_QUANTITY}\s*{_UNIT}\s+(?i:jar)'),
        re.compile(
            rf'(?i:powder)\s+(?i:in)\s+(?i:a)\s+{_QUANTITY}\s*{_UNIT}\s+(?i:jar)'
        ),
    ),
    'F02': (re.compile(rf'(?i:capsules)\s*,\s*{_QUANTITY}\s*{_UNIT}'),),
    'F03': (
        re.compile(rf'(?i:paste)\s*,\s*{_QUANTITY}\s*{_UNIT}\s+(?i:tube)'),
        re.compile(
            rf'(?i:paste)\s+(?i:in)\s+(?i:a)\s+{_QUANTITY}\s*{_UNIT}\s+(?i:tube)'
        ),
    ),
    'F04': (re.compile(rf'(?i:steel)\s+(?i:spoon)\s*,\s*{_QUANTITY}\s*{_UNIT}'),),
    'F05': (re.compile(rf'(?i:plastic)\s+(?i:box)\s*,\s*{_QUANTITY}\s*{_UNIT}'),),
    'F06': (
        re.compile(rf'(?i:зерно)\s*,\s*(?i:пачка)\s+{_QUANTITY}\s*{_UNIT}'),
        re.compile(rf'(?i:зерно)\s+(?i:в)\s+(?i:пачке)\s+{_QUANTITY}\s*{_UNIT}'),
    ),
    'F07': (re.compile(rf'(?i:упаковка)\s+{_QUANTITY}\s*{_UNIT}'),),
    'F08': (
        re.compile(
            rf'(?i:стальные)\s+(?i:жернова)\s*,\s*{_QUANTITY}\s*{_UNIT}'
            rf'\s+(?i:за)\s+(?i:раз)'
        ),
    ),
}


def _form_at(text: str, position: int, profile_id: str) -> re.Match[str] | None:
    """Match one form profile."""
    if position > 0 and _is_letter(text[position - 1]):
        return None
    for core in _FORM_CORES[profile_id]:
        match = core.match(text, position)
        if match is None:
            continue
        if match.end() < len(text) and _is_letter(text[match.end()]):
            continue
        return match
    return None


# === Token matchers N01 ===

_WORD_CACHE: dict[str, re.Pattern[str]] = {}


def _word_pattern(word: str) -> re.Pattern[str]:
    """Compile one word pattern."""
    pattern = _WORD_CACHE.get(word)
    if pattern is None:
        pattern = re.compile(rf'(?i:{re.escape(word)})')
        _WORD_CACHE[word] = pattern
    return pattern


def _word_at(text: str, position: int, word: str) -> int | None:
    """Match one fixed word."""
    match = _word_pattern(word).match(text, position)
    if match is None:
        return None
    end = match.end()
    if position > 0 and _is_letter(text[position - 1]):
        return None
    if end < len(text) and _is_letter(text[end]):
        return None
    return end


def _name_at(text: str, position: int, name: str) -> int | None:
    """Match one product name."""
    if not text.startswith(name, position):
        return None
    end = position + len(name)
    if position > 0 and _is_letter(text[position - 1]):
        return None
    if end < len(text) and _is_letter(text[end]):
        return None
    return end


def _spaces_at(text: str, position: int) -> int | None:
    """Match required spaces."""
    match = _SPACES_RE.match(text, position)
    return None if match is None else match.end()


def _skip_spaces(text: str, position: int) -> int:
    """Skip optional spaces."""
    match = _SPACES_RE.match(text, position)
    return position if match is None else match.end()


def _words_at(
    text: str, position: int, words: tuple[str, ...], leading: bool = False
) -> int | None:
    """Match spaced fixed words."""
    start = _spaces_at(text, position) if leading else position
    if start is None:
        return None
    cursor: int | None = _word_at(text, start, words[0])
    if cursor is None:
        return None
    for word in words[1:]:
        gap = _spaces_at(text, cursor)
        if gap is None:
            return None
        cursor = _word_at(text, gap, word)
        if cursor is None:
            return None
    return cursor


def _article_at(text: str, position: int) -> int:
    """Match one optional article."""
    for article in ('an', 'a'):
        end = _word_at(text, position, article)
        if end is not None:
            after = _spaces_at(text, end)
            if after is not None:
                return after
    return position


def _colon_at(text: str, position: int) -> int | None:
    """Match one spacing colon."""
    cursor = _skip_spaces(text, position)
    if not text.startswith(':', cursor):
        return None
    return _skip_spaces(text, cursor + 1)


def _comma_at(text: str, position: int) -> int | None:
    """Match one spacing comma."""
    cursor = _skip_spaces(text, position)
    if not text.startswith(',', cursor):
        return None
    return _skip_spaces(text, cursor + 1)


def _price_tail(text: str, position: int, word: str) -> tuple[Decimal, str, int] | None:
    """Match word with price."""
    cursor = _word_at(text, position, word)
    if cursor is None:
        return None
    gap = _spaces_at(text, cursor)
    if gap is None:
        return None
    return _price_at(text, gap)


# === Claim builders ===


def _claim(
    product_id: str,
    kind: ClaimKind,
    span: tuple[int, int],
    expected: str,
    found: str,
    matches: bool,
) -> Claim:
    """Build one typed claim."""
    return Claim(
        product_id=product_id,
        kind=kind,
        start=span[0],
        end=span[1],
        expected=expected,
        found=found,
        matches=matches,
    )


def _price_claim(
    product: VerifiedProductFacts, span: tuple[int, int], value: Decimal, currency: str
) -> Claim:
    """Build one price claim."""
    price = cast('PriceValue', product.price)
    expected = f'{price.value} {price.currency}'
    found = f'{value} {currency}'
    return Claim(
        product_id=product.product_id,
        kind='price',
        start=span[0],
        end=span[1],
        expected=expected,
        found=found,
        matches=value == price.value and currency == price.currency,
    )


def _form_claim(
    product: VerifiedProductFacts,
    span: tuple[int, int],
    found: str,
    quantity: int,
    unit: str,
) -> Claim:
    """Build one form claim."""
    predicate = _QUANTITY_PREDICATES[product.profile_id]
    expected_count = product.count(predicate)
    return Claim(
        product_id=product.product_id,
        kind='form',
        start=span[0],
        end=span[1],
        expected=product.text('form') or '',
        found=found,
        matches=expected_count == (quantity, unit),
    )


def _form_result(
    fragment: str, product: VerifiedProductFacts, form: re.Match[str]
) -> tuple[list[Claim], int]:
    """Build one form result."""
    quantity = int(form.group('quantity'))
    unit = _UNITS[form.group('unit')]
    found = fragment[form.start() : form.end()]
    claim = _form_claim(product, (0, form.end()), found, quantity, unit)
    return [claim], form.end()


def _compound_claims(
    fragment: str,
    product: VerifiedProductFacts,
    form: re.Match[str],
    value: Decimal,
    currency: str,
    end: int,
) -> tuple[list[Claim], int]:
    """Build compound claims."""
    quantity = int(form.group('quantity'))
    unit = _UNITS[form.group('unit')]
    found = fragment[form.start() : form.end()]
    claims = [
        _form_claim(product, (0, end), found, quantity, unit),
        _price_claim(product, (0, end), value, currency),
    ]
    return claims, end


# === Construction parsing ===


def _compound_comes_as(
    fragment: str, product: VerifiedProductFacts, name: str
) -> tuple[list[Claim], int] | None:
    """Parse comes as compound."""
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    cursor = _words_at(fragment, cursor, ('comes', 'as'), True)
    if cursor is None:
        return None
    gap = _spaces_at(fragment, cursor)
    if gap is None:
        return None
    cursor = _article_at(fragment, gap)
    form = _form_at(fragment, cursor, product.profile_id)
    if form is None:
        return None
    cursor = _words_at(fragment, form.end(), ('and', 'costs'), True)
    if cursor is None:
        return None
    gap = _spaces_at(fragment, cursor)
    if gap is None:
        return None
    price = _price_at(fragment, gap)
    if price is None:
        return None
    value, currency, end = price
    return _compound_claims(fragment, product, form, value, currency, end)


def _compound_colon(
    fragment: str, product: VerifiedProductFacts, name: str
) -> tuple[list[Claim], int] | None:
    """Parse colon compound."""
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    cursor = _colon_at(fragment, cursor)
    if cursor is None:
        return None
    cursor = _article_at(fragment, cursor)
    form = _form_at(fragment, cursor, product.profile_id)
    if form is None:
        return None
    cursor = _comma_at(fragment, form.end())
    if cursor is None:
        return None
    price = _price_tail(fragment, cursor, 'цена')
    if price is None:
        return None
    value, currency, end = price
    return _compound_claims(fragment, product, form, value, currency, end)


def _parse_compound(
    fragment: str, product: VerifiedProductFacts, name: str
) -> tuple[list[Claim], int] | None:
    """Parse one compound construction."""
    for builder in (_compound_comes_as, _compound_colon):
        parsed = builder(fragment, product, name)
        if parsed is not None:
            return parsed
    return None


def _parse_form(
    fragment: str, product: VerifiedProductFacts, name: str
) -> tuple[list[Claim], int] | None:
    """Parse one form construction."""
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    for words, article in (
        (('comes', 'as'), True),
        (('выпускается', 'в', 'форме'), False),
    ):
        intro = _words_at(fragment, cursor, words, True)
        if intro is None:
            continue
        gap = _spaces_at(fragment, intro)
        if gap is None:
            continue
        start = _article_at(fragment, gap) if article else gap
        form = _form_at(fragment, start, product.profile_id)
        if form is not None:
            return _form_result(fragment, product, form)
    colon = _colon_at(fragment, cursor)
    if colon is None:
        return None
    start = _article_at(fragment, colon)
    form = _form_at(fragment, start, product.profile_id)
    if form is None:
        return None
    return _form_result(fragment, product, form)


def _parse_price(
    fragment: str, product: VerifiedProductFacts, name: str
) -> tuple[list[Claim], int] | None:
    """Parse one price construction."""
    cursor = _name_at(fragment, 0, name)
    if cursor is not None:
        for word in ('costs', 'стоит'):
            gap = _spaces_at(fragment, cursor)
            if gap is None:
                continue
            price = _price_tail(fragment, gap, word)
            if price is not None:
                return _price_result(product, price)
        colon = _colon_at(fragment, cursor)
        if colon is not None:
            price = _price_tail(fragment, colon, 'цена')
            if price is not None:
                return _price_result(product, price)
        return None
    intro = _words_at(fragment, 0, ('the', 'price', 'of'))
    if intro is not None:
        gap = _spaces_at(fragment, intro)
        if gap is not None:
            after_name = _name_at(fragment, gap, name)
            if after_name is not None:
                second_gap = _spaces_at(fragment, after_name)
                if second_gap is not None:
                    price = _price_tail(fragment, second_gap, 'is')
                    if price is not None:
                        return _price_result(product, price)
    intro_word = _word_at(fragment, 0, 'Цена')
    if intro_word is not None:
        gap = _spaces_at(fragment, intro_word)
        if gap is not None:
            after_name = _name_at(fragment, gap, name)
            if after_name is not None:
                colon = _colon_at(fragment, after_name)
                if colon is not None:
                    price = _price_at(fragment, colon)
                    if price is not None:
                        return _price_result(product, price)
    return None


def _price_result(
    product: VerifiedProductFacts, price: tuple[Decimal, str, int]
) -> tuple[list[Claim], int]:
    """Build one price result."""
    value, currency, end = price
    claim = _price_claim(product, (0, end), value, currency)
    return [claim], end


def _parse_construction(
    fragment: str, product: VerifiedProductFacts
) -> tuple[list[Claim], int] | None:
    """Parse one anchored construction."""
    name = product.text('name')
    if name is None or product.price is None:
        return None
    compound = _parse_compound(fragment, product, name)
    if compound is not None:
        return compound
    form = _parse_form(fragment, product, name)
    if form is not None:
        return form
    return _parse_price(fragment, product, name)


# === Policy templates R09 to R12 ===

_PLACE = r'[^\W\d_]+(?:[\s\-]+[^\W\d_]+)*'
_ABSENCE_DELIVERY_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf'I\s+do\s+not\s+have\s+information\s+about\s+delivery\s+to\s+(?P<place>{_PLACE})\s+or\s+delivery\s+times',
        re.IGNORECASE,
    ),
    re.compile(
        rf'В\s+базе\s+нет\s+информации\s+о\s+доставке\s+в\s+(?P<place>{_PLACE})\s+и\s+сроках',
        re.IGNORECASE,
    ),
)
_ABSENCE_STOCK_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf'I\s+do\s+not\s+have\s+stock\s+information\s+for\s+(?P<name>{_PLACE})',
        re.IGNORECASE,
    ),
    re.compile(
        rf'В\s+базе\s+нет\s+информации\s+о\s+наличии\s+(?P<name>{_PLACE})',
        re.IGNORECASE,
    ),
)
_DELIVERY_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf'We\s+deliver\s+to\s+(?P<place>{_PLACE})', re.IGNORECASE),
    re.compile(
        rf'Delivery\s+to\s+(?P<place>{_PLACE})\s+takes\s+[1-9]\d*\s+days',
        re.IGNORECASE,
    ),
    re.compile(rf'У\s+нас\s+есть\s+доставка\s+в\s+(?P<place>{_PLACE})', re.IGNORECASE),
    re.compile(
        rf'Доставка\s+в\s+(?P<place>{_PLACE})\s*:\s*[1-9]\d*\s+дней', re.IGNORECASE
    ),
)


def _product_named(index: VerifiedFactIndex, name: str) -> VerifiedProductFacts | None:
    """Find one product by name."""
    for product in index.products.values():
        if product.text('name') == name:
            return product
    return None


def _absence_claim(fragment: str, start: int, index: VerifiedFactIndex) -> Claim | None:
    """Parse one absence template."""
    for pattern in _ABSENCE_DELIVERY_RES:
        if pattern.fullmatch(fragment) is not None:
            return _claim(
                '',
                'absence_delivery',
                (start, start + len(fragment)),
                'no delivery information',
                fragment,
                True,
            )
    for pattern in _ABSENCE_STOCK_RES:
        match = pattern.fullmatch(fragment)
        if match is None:
            continue
        product = _product_named(index, match.group('name'))
        if product is None:
            return None
        return _claim(
            product.product_id,
            'absence_stock',
            (start, start + len(fragment)),
            'no stock information',
            fragment,
            product.support.get('stock') == 'absent',
        )
    return None


def _delivery_claim(fragment: str, start: int) -> Claim | None:
    """Parse one delivery affirmation."""
    for pattern in _DELIVERY_RES:
        if pattern.fullmatch(fragment) is not None:
            return _claim(
                '',
                'delivery',
                (start, start + len(fragment)),
                'no delivery information',
                fragment,
                False,
            )
    return None


# === Service phrases R14 ===

_SERVICE_PHRASES: tuple[
    tuple[tuple[str, ...], PolicyLanguage, bool, str | None], ...
] = (
    (('Hello',), 'en', False, None),
    (('Здравствуйте',), 'ru', False, None),
    (
        ('I', 'can', 'pass', 'the', 'question', 'to', 'a', 'manager'),
        'en',
        True,
        'handoff',
    ),
    (('Могу', 'передать', 'вопрос', 'менеджеру'), 'ru', True, 'handoff'),
    (
        ('Please', 'ask', 'a', 'doctor', 'about', 'health', 'questions'),
        'en',
        True,
        'doctor',
    ),
)
_SERVICE_ACTIONS: dict[str, str] = {
    ' '.join(words): action
    for words, _language, _any_field, action in _SERVICE_PHRASES
    if action is not None
}


def _service_claim(
    fragment: str, start: int, field: FieldName, language: PolicyLanguage
) -> Claim | None:
    """Parse one service phrase."""
    for words, phrase_language, any_field, _action in _SERVICE_PHRASES:
        if phrase_language != language:
            continue
        if field == 'upsell_hint' and not any_field:
            continue
        end = _words_at(fragment, 0, words)
        if end == len(fragment):
            return _claim(
                '',
                'service',
                (start, start + len(fragment)),
                ' '.join(words),
                fragment,
                True,
            )
    return None


# === Hint directive R13 ===


def _directive_claim(
    fragment: str,
    start: int,
    index: VerifiedFactIndex,
    field: FieldName,
    upsell_product_id: str | None,
) -> Claim | None:
    """Parse one manager directive."""
    if field != 'upsell_hint' or upsell_product_id is None:
        return None
    for verb in ('Offer', 'Consider', 'Предложите'):
        verb_end = _word_at(fragment, 0, verb)
        if verb_end is None:
            continue
        gap = _spaces_at(fragment, verb_end)
        if gap is None:
            continue
        for product in index.products.values():
            name = product.text('name')
            if name is None:
                continue
            name_end = _name_at(fragment, gap, name)
            if name_end == len(fragment):
                return _claim(
                    upsell_product_id,
                    'directive',
                    (start, start + len(fragment)),
                    upsell_product_id,
                    product.product_id,
                    product.product_id == upsell_product_id,
                )
    return None


# === Typed constructions R04 to R09 ===


def _description_claim(
    fragment: str, start: int, product: VerifiedProductFacts
) -> Claim | None:
    """Parse one description quote."""
    description = product.text('description')
    name = product.text('name')
    if description is None or name is None:
        return None
    anchors: list[int | None] = [_name_at(fragment, 0, name)]
    for words in (('Description', 'of'), ('Описание',)):
        intro = _words_at(fragment, 0, words)
        gap = None if intro is None else _spaces_at(fragment, intro)
        anchors.append(None if gap is None else _name_at(fragment, gap, name))
    for anchor in anchors:
        if anchor is None:
            continue
        colon = _colon_at(fragment, anchor)
        if colon is None:
            continue
        rest = fragment[colon:]
        if _description_matches(rest, description):
            return _claim(
                product.product_id,
                'description',
                (start, start + len(fragment)),
                description,
                rest,
                True,
            )
    return None


def _description_matches(rest: str, description: str) -> bool:
    """Compare one description quote."""
    body = description[:-1] if description[-1:] in _SEPARATORS else description
    if not body or len(rest) != len(body):
        return False
    return rest[1:] == body[1:] and rest[0].casefold() == body[0].casefold()


def _batch_claim(
    fragment: str, start: int, product: VerifiedProductFacts
) -> Claim | None:
    """Parse one batch claim."""
    expected = product.count('batch_capacity')
    name = product.text('name')
    if expected is None or name is None:
        return None
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    for verb, tail in (('перемалывает', ('за', 'раз')), ('grinds', ('per', 'batch'))):
        gap = _spaces_at(fragment, cursor)
        if gap is None:
            continue
        verb_end = _word_at(fragment, gap, verb)
        if verb_end is None:
            continue
        mass = _mass_at(fragment, verb_end, integer=True)
        if mass is None:
            continue
        value, unit, value_start, unit_end = mass
        tail_end = _words_at(fragment, unit_end, tail, leading=True)
        if tail_end != len(fragment):
            continue
        return _claim(
            product.product_id,
            'batch_capacity',
            (start, start + len(fragment)),
            f'{expected[0]} {expected[1]}',
            fragment[value_start:unit_end],
            (int(value), unit) == expected,
        )
    return None


def _mass_claim(
    fragment: str, start: int, product: VerifiedProductFacts
) -> Claim | None:
    """Parse one mass claim."""
    name = product.text('name')
    if name is None:
        return None
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    for verb in ('весит', 'weighs'):
        gap = _spaces_at(fragment, cursor)
        if gap is None:
            continue
        verb_end = _word_at(fragment, gap, verb)
        if verb_end is None:
            continue
        mass = _mass_at(fragment, verb_end, integer=False)
        if mass is None:
            continue
        value, unit, value_start, unit_end = mass
        if unit_end != len(fragment):
            continue
        if product.support.get('object_mass') == 'unresolved':
            return None
        typed = product.count('object_mass')
        expected = f'{typed[0]} {typed[1]}' if typed is not None else 'no object mass'
        return _claim(
            product.product_id,
            'object_mass',
            (start, start + len(fragment)),
            expected,
            fragment[value_start:unit_end],
            typed is not None and value == Decimal(typed[0]) and unit == typed[1],
        )
    return None


def _filter_claim(
    fragment: str, start: int, product: VerifiedProductFacts
) -> Claim | None:
    """Parse one filter claim."""
    name = product.text('name')
    code = product.text('filter_size')
    if name is None or code is None:
        return None
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    for words in (('для', 'воронки', 'размера'), ('for', 'filter', 'size')):
        tail = _words_at(fragment, cursor, words, leading=True)
        if tail is None:
            continue
        gap = _spaces_at(fragment, tail)
        if gap is None:
            continue
        match = _DIGITS_RE.match(fragment, gap)
        if match is None or match.end() != len(fragment):
            continue
        return _claim(
            product.product_id,
            'filter_size',
            (start, start + len(fragment)),
            code,
            match.group(0),
            match.group(0) == code,
        )
    return None


def _stock_claim(
    fragment: str, start: int, product: VerifiedProductFacts
) -> Claim | None:
    """Parse one stock claim."""
    name = product.text('name')
    if name is None:
        return None
    cursor = _name_at(fragment, 0, name)
    if cursor is None:
        return None
    for words in (('is', 'in', 'stock'), ('есть', 'в', 'наличии')):
        tail = _words_at(fragment, cursor, words, leading=True)
        if tail == len(fragment):
            return _claim(
                product.product_id,
                'stock',
                (start, start + len(fragment)),
                'no stock information',
                fragment,
                False,
            )
    return None


def _relation_claim(
    fragment: str, start: int, index: VerifiedFactIndex
) -> Claim | None:
    """Parse one relation claim."""
    for source in index.products.values():
        name = source.text('name')
        if name is None:
            continue
        cursor = _name_at(fragment, 0, name)
        if cursor is None:
            continue
        for words in (('pairs', 'with'), ('сочетается', 'с')):
            connector = _words_at(fragment, cursor, words, leading=True)
            if connector is None:
                continue
            gap = _spaces_at(fragment, connector)
            if gap is None:
                continue
            for target in index.products.values():
                target_name = target.text('name')
                if target_name is None or target is source:
                    continue
                target_end = _name_at(fragment, gap, target_name)
                if target_end == len(fragment):
                    return _claim(
                        source.product_id,
                        'relation',
                        (start, start + len(fragment)),
                        target.product_id,
                        target_name,
                        target.product_id in source.edges,
                    )
    return None


# === Disclaimer R15 ===


def _disclaimer_ranges(
    text: str, policy: SourcePolicy | None
) -> tuple[tuple[int, int], ...]:
    """Locate disclaimer occurrence ranges."""
    if policy is None or not policy.disclaimer:
        return ()
    ranges: list[tuple[int, int]] = []
    offset = text.find(policy.disclaimer)
    while offset != -1:
        ranges.append((offset, offset + len(policy.disclaimer)))
        offset = text.find(policy.disclaimer, offset + 1)
    return tuple(ranges)


def _disclaimer_claim(text: str, policy: SourcePolicy) -> Claim | None:
    """Check the disclaimer suffix."""
    disclaimer = policy.disclaimer
    if policy.stage != 'final_suggestion' or not disclaimer:
        return None
    ends_with = text.endswith(disclaimer)
    start = len(text) - len(disclaimer) if ends_with else len(text)
    return _claim(
        '',
        'disclaimer',
        (start, len(text)),
        disclaimer,
        text[start:] if ends_with else '',
        text.endswith(f'\n\n{disclaimer}'),
    )


# === Field assessment ===


def _contains_name(fragment: str, product: VerifiedProductFacts) -> bool:
    """Report one subject name."""
    name = product.text('name')
    if name is None:
        return False
    position = fragment.find(name)
    return position >= 0 and _name_at(fragment, position, name) is not None


def _subject_products(
    fragment: str, index: VerifiedFactIndex
) -> list[VerifiedProductFacts]:
    """Collect the named subjects."""
    return [
        product
        for product in index.products.values()
        if _contains_name(fragment, product)
    ]


def _inside_ranges(start: int, end: int, ranges: Sequence[tuple[int, int]]) -> bool:
    """Report one covered span."""
    return any(low <= start and end <= high for low, high in ranges)


def _excluded_ranges(
    text: str, index: VerifiedFactIndex, policy: SourcePolicy | None
) -> tuple[tuple[int, int], ...]:
    """Collect the masked policy ranges."""
    ranges: list[tuple[int, int]] = []
    for start, end in _statements(text):
        if _absence_claim(text[start:end], start, index) is not None:
            ranges.append((start, end))
    ranges.extend(_disclaimer_ranges(text, policy))
    return tuple(ranges)


def _parse_fragment(
    text: str,
    start: int,
    end: int,
    index: VerifiedFactIndex,
    field: FieldName,
    upsell_product_id: str | None,
) -> tuple[list[Claim], tuple[int, int] | None]:
    """Parse one statement fragment."""
    fragment = text[start:end]
    absence = _absence_claim(fragment, start, index)
    if absence is not None:
        return [absence], None
    delivery = _delivery_claim(fragment, start)
    if delivery is not None:
        return [delivery], None
    subjects = _subject_products(fragment, index)
    if len(subjects) == 2:
        relation = _relation_claim(fragment, start, index)
        if relation is not None:
            return [relation], None
        return [], (start, end)
    if len(subjects) != 1:
        return [], (start, end)
    product = subjects[0]
    directive = _directive_claim(fragment, start, index, field, upsell_product_id)
    if directive is not None:
        return [directive], None
    parsed = _parse_construction(fragment, product)
    if parsed is not None:
        claims, match_end = parsed
        offset_claims = [
            replace(claim, start=claim.start + start, end=claim.end + start)
            for claim in claims
        ]
        remainder_start, remainder_end = _trim_span(text, start + match_end, end)
        if remainder_start >= remainder_end:
            return offset_claims, None
        return offset_claims, (remainder_start, remainder_end)
    for builder in (
        _description_claim,
        _batch_claim,
        _mass_claim,
        _filter_claim,
        _stock_claim,
    ):
        claim = builder(fragment, start, product)
        if claim is not None:
            return [claim], None
    return [], (start, end)


def _check_field(field: str) -> None:
    """Validate one field name."""
    if field not in ('customer_reply', 'upsell_hint'):
        raise ValueError(f'unknown field: {field}')


def _check_policy(policy: SourcePolicy) -> None:
    """Validate one source policy."""
    if policy.stage not in (None, 'model_output', 'final_suggestion'):
        raise ValueError(f'unknown stage: {policy.stage}')
    if policy.language not in ('en', 'ru'):
        raise ValueError(f'unknown language: {policy.language}')


def assess_field(
    text: str,
    index: VerifiedFactIndex,
    field: FieldName = 'customer_reply',
    upsell_product_id: str | None = None,
    source_policy: SourcePolicy | None = None,
) -> FieldAssessment:
    """Assess one answer field."""
    _check_field(field)
    if source_policy is not None:
        _check_policy(source_policy)
    language = source_policy.language if source_policy is not None else 'en'
    excluded = _excluded_ranges(text, index, source_policy)
    reason = _protection_reason(text, excluded)
    if reason is not None:
        whole = ((0, len(text)),) if text else ()
        return FieldAssessment(
            protected=True,
            protection_reason=reason,
            claims=(),
            service_fragments=(),
            remainders=whole,
        )
    claims: list[Claim] = []
    remainders: list[tuple[int, int]] = []
    service_claims: list[Claim] = []
    only_service = True
    disclaimer = (
        _disclaimer_claim(text, source_policy) if source_policy is not None else None
    )
    skip_ranges = (
        _disclaimer_ranges(text, source_policy) if disclaimer is not None else ()
    )
    for start, end in _statements(text):
        if _inside_ranges(start, end, skip_ranges):
            continue
        fragment = text[start:end]
        service = _service_claim(fragment, start, field, language)
        if service is not None:
            service_claims.append(service)
            continue
        only_service = False
        fragment_claims, remainder = _parse_fragment(
            text, start, end, index, field, upsell_product_id
        )
        claims.extend(fragment_claims)
        if remainder is not None:
            remainders.append(remainder)
    if only_service:
        claims.extend(service_claims)
    service_fragments = tuple(service_claims)
    if disclaimer is not None:
        claims.append(disclaimer)
    return FieldAssessment(
        protected=False,
        protection_reason=None,
        claims=tuple(claims),
        service_fragments=service_fragments,
        remainders=tuple(remainders),
    )


# === Answer aggregation ===

_OBLIGATION_KINDS: dict[str, frozenset[str]] = {
    'price': frozenset({'price'}),
    'form': frozenset({'form'}),
    'package_quantity': frozenset({'form'}),
    'form_quantity': frozenset({'form'}),
    'batch_capacity': frozenset({'batch_capacity', 'form'}),
    'section_count': frozenset({'form'}),
    'description': frozenset({'description'}),
    'goes_with': frozenset({'relation'}),
}
_ABSENCE_KINDS: dict[str, str] = {
    'delivery': 'absence_delivery',
    'stock': 'absence_stock',
}
_DOMAIN_KINDS = frozenset({'stock', 'delivery'})


def _field_claims(assessment: FieldAssessment) -> tuple[Claim, ...]:
    """Collect every field claim."""
    return (*assessment.claims, *assessment.service_fragments)


def _fully_parsed(assessment: FieldAssessment) -> bool:
    """Report one complete parse."""
    return not assessment.protected and not assessment.remainders


def _split_claims(
    obligation: RequiredClaim, assessment: FieldAssessment
) -> tuple[list[Claim], list[Claim]]:
    """Split claims by matching."""
    kinds = _OBLIGATION_KINDS.get(
        obligation.predicate, frozenset({obligation.predicate})
    )
    matching: list[Claim] = []
    contradicting: list[Claim] = []
    for claim in assessment.claims:
        if claim.kind not in kinds:
            continue
        if (
            obligation.product_id is not None
            and claim.product_id != obligation.product_id
        ):
            continue
        if obligation.predicate == 'goes_with' and (
            obligation.target_product_id is not None
            and claim.expected != obligation.target_product_id
        ):
            continue
        if claim.matches:
            matching.append(claim)
        else:
            contradicting.append(claim)
    return matching, contradicting


def _obligation_label(obligation: RequiredClaim) -> str:
    """Name one claim obligation."""
    if obligation.product_id is None:
        return obligation.predicate
    return f'{obligation.predicate} of {obligation.product_id}'


def _action_satisfied(
    action: RequiredAction, fields: dict[str, FieldAssessment]
) -> bool:
    """Report one satisfied action."""
    assessment = fields[action.field]
    if assessment.protected:
        return False
    for claim in assessment.service_fragments:
        if (
            claim.kind == 'service'
            and claim.matches
            and (_SERVICE_ACTIONS.get(claim.expected) == action.kind)
        ):
            return True
    return False


def _unknown_satisfied(
    obligation: RequiredClaim,
    assessment: FieldAssessment,
    question: AssessmentQuestion,
    fields: dict[str, FieldAssessment],
) -> bool:
    """Check one unknown stance."""
    absence_kind = _ABSENCE_KINDS.get(obligation.predicate)
    if absence_kind is not None:
        for claim in assessment.claims:
            if claim.kind == absence_kind and claim.matches:
                return True
    return any(
        _action_satisfied(action, fields)
        for action in question.required_actions
        if action.field == obligation.field
    )


def _resolve_claim_obligation(
    obligation: RequiredClaim,
    question: AssessmentQuestion,
    fields: dict[str, FieldAssessment],
    grounds: list[str],
    unresolved: list[str],
) -> None:
    """Resolve one claim obligation."""
    assessment = fields[obligation.field]
    label = _obligation_label(obligation)
    if assessment.protected:
        unresolved.append(f'unresolved_obligation: {label}')
        return
    if obligation.stance == 'unknown':
        satisfied = _unknown_satisfied(obligation, assessment, question, fields)
        contradicting: list[Claim] = []
    else:
        matching, contradicting = _split_claims(obligation, assessment)
        satisfied = bool(matching)
    if satisfied or contradicting:
        return
    if _fully_parsed(assessment):
        grounds.append('incompleteness')
    else:
        unresolved.append(f'unresolved_obligation: {label}')


def _resolve_action_obligation(
    action: RequiredAction,
    fields: dict[str, FieldAssessment],
    grounds: list[str],
    unresolved: list[str],
) -> None:
    """Resolve one action obligation."""
    if _action_satisfied(action, fields):
        return
    assessment = fields[action.field]
    if _fully_parsed(assessment):
        grounds.append('incompleteness')
    else:
        unresolved.append(f'unresolved_action: {action.kind}')


def assess_answer(
    customer: FieldAssessment,
    hint: FieldAssessment,
    question: AssessmentQuestion,
    answer: Answer,
    index: VerifiedFactIndex,
    source_policy: SourcePolicy | None = None,
) -> AnswerAssessment:
    """Aggregate one answer verdict."""
    if source_policy is not None:
        _check_policy(source_policy)
    fields = {'customer_reply': customer, 'upsell_hint': hint}
    texts = {
        'customer_reply': answer.customer_reply,
        'upsell_hint': answer.upsell_hint,
    }
    grounds: list[str] = []
    unresolved: list[str] = []
    # Step 1: establish proven claim errors by A02 and A06.
    for name, assessment in fields.items():
        if assessment.protected:
            unresolved.append(f'protected_context: {name}')
            continue
        for claim in _field_claims(assessment):
            if claim.matches:
                continue
            if claim.kind in _DOMAIN_KINDS:
                grounds.append('domain')
            else:
                grounds.append(
                    f'{claim.kind}_mismatch: expected {claim.expected}, '
                    f'found {claim.found}'
                )
    # Step 2: check the metadata obligations by M01 and M02.
    if answer.upsell_product_id is not None and (
        answer.upsell_product_id not in index.products
    ):
        grounds.append('metadata_upsell')
    if answer.kb_match not in question.allowed_kb_matches:
        grounds.append('metadata_kb_match')
    # Step 3: resolve the claim obligations by M03 and M04.
    for obligation in question.required_claims:
        _resolve_claim_obligation(obligation, question, fields, grounds, unresolved)
    # Step 4: resolve the action obligations.
    for action in question.required_actions:
        _resolve_action_obligation(action, fields, grounds, unresolved)
    # Step 5: preserve every unchecked tail by A03.
    for name, assessment in fields.items():
        if assessment.protected:
            continue
        text = texts[name]
        for start, end in assessment.remainders:
            unresolved.append(f'remainder: {name}: {text[start:end]}')
    # Step 6: a proven error outranks preserved uncertainty by A02.
    ordered_grounds = tuple(dict.fromkeys(grounds))
    kept = tuple(dict.fromkeys(unresolved))
    if ordered_grounds:
        verdict: Verdict = 'error'
    elif kept:
        verdict = 'manual_review'
    else:
        verdict = 'confirmed'
    return AnswerAssessment(verdict=verdict, grounds=ordered_grounds, unresolved=kept)
