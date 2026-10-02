"""Finite answer grammar."""

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal, cast

from reply_assistant.quality_facts import (
    PriceValue,
    VerifiedFactIndex,
    VerifiedProductFacts,
)

# === Assessment models ===

ClaimKind = Literal['price', 'form']
ProtectionReason = Literal['quote', 'negation', 'condition', 'question']


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
    remainders: tuple[tuple[int, int], ...]


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


def _protection_reason(text: str) -> ProtectionReason | None:
    """Find the protection reason."""
    if _has_quote_marker(text):
        return 'quote'
    for marker, reason in _MARKER_KINDS:
        if _MARKER_RES[marker].search(text):
            return reason
    if '?' in text:
        return 'question'
    return None


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


# === Field assessment ===


def _contains_name(fragment: str, product: VerifiedProductFacts) -> bool:
    """Report one subject name."""
    name = product.text('name')
    if name is None:
        return False
    position = fragment.find(name)
    return position >= 0 and _name_at(fragment, position, name) is not None


def _parse_fragment(
    text: str, start: int, end: int, index: VerifiedFactIndex
) -> tuple[list[Claim], tuple[int, int] | None]:
    """Parse one statement fragment."""
    fragment = text[start:end]
    subjects = [
        product
        for product in index.products.values()
        if _contains_name(fragment, product)
    ]
    if len(subjects) != 1:
        return [], (start, end)
    parsed = _parse_construction(fragment, subjects[0])
    if parsed is None:
        return [], (start, end)
    claims, match_end = parsed
    offset_claims = [
        replace(claim, start=claim.start + start, end=claim.end + start)
        for claim in claims
    ]
    remainder_start, remainder_end = _trim_span(text, start + match_end, end)
    if remainder_start >= remainder_end:
        return offset_claims, None
    return offset_claims, (remainder_start, remainder_end)


def assess_field(text: str, index: VerifiedFactIndex) -> FieldAssessment:
    """Assess one answer field."""
    reason = _protection_reason(text)
    if reason is not None:
        whole = ((0, len(text)),) if text else ()
        return FieldAssessment(
            protected=True,
            protection_reason=reason,
            claims=(),
            remainders=whole,
        )
    claims: list[Claim] = []
    remainders: list[tuple[int, int]] = []
    for start, end in _statements(text):
        fragment_claims, remainder = _parse_fragment(text, start, end, index)
        claims.extend(fragment_claims)
        if remainder is not None:
            remainders.append(remainder)
    return FieldAssessment(
        protected=False,
        protection_reason=None,
        claims=tuple(claims),
        remainders=tuple(remainders),
    )
