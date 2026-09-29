"""Knowledge base loading."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# === Error ===


class KnowledgeBaseError(Exception):
    """Invalid knowledge base file."""

    def __init__(self, message: str, field: str | None) -> None:
        """Keep the message and the field."""
        super().__init__(message)
        self.field = field


# === Model ===


@dataclass(frozen=True)
class Product:
    """A product of the catalogue."""

    id: str
    name: str
    form: str
    price: str
    description: str
    goes_with: list[str]


@dataclass(frozen=True)
class KnowledgeBase:
    """The loaded knowledge base."""

    company: str
    language: str
    reply_rules: list[str]
    forbidden_claims: list[str]
    products: list[Product]
    disclaimer: str | None


# === Validation ===

TOP_KEYS = {
    'company',
    'language',
    'reply_rules',
    'forbidden_claims',
    'products',
    'disclaimer',
}
PRODUCT_KEYS = {'id', 'name', 'form', 'price', 'description', 'goes_with'}


def _text(value: Any, field: str) -> str:
    """Check one required text value."""
    if not isinstance(value, str) or not value:
        raise KnowledgeBaseError(f'{field} must be a non-empty string', field)
    return value


def _required(mapping: dict[Any, Any], key: str, field: str) -> Any:
    """Fetch one required key."""
    if key not in mapping:
        raise KnowledgeBaseError(f'{field} is missing', field)
    return mapping[key]


def _known_keys(mapping: dict[Any, Any], keys: set[str], prefix: str) -> None:
    """Reject unknown mapping keys."""
    for key in mapping:
        if key not in keys:
            field = f'{prefix}{key}'
            raise KnowledgeBaseError(f'{field} is not a known key', field)


def _text_list(value: Any, field: str) -> list[str]:
    """Check a list of text values."""
    if not isinstance(value, list):
        raise KnowledgeBaseError(f'{field} must be a list', field)
    return [_text(entry, f'{field}.{index}') for index, entry in enumerate(value)]


def _product(entry: Any, index: int, known_ids: set[str]) -> Product:
    """Check one product entry."""
    base = f'products.{index}'
    if not isinstance(entry, dict):
        raise KnowledgeBaseError(f'{base} must be a mapping', base)
    _known_keys(entry, PRODUCT_KEYS, f'{base}.')
    product_id = _text(_required(entry, 'id', f'{base}.id'), f'{base}.id')
    if product_id in known_ids:
        raise KnowledgeBaseError(f'{base}.id repeats the id {product_id}', f'{base}.id')
    known_ids.add(product_id)
    goes_with: list[str] = []
    raw = entry.get('goes_with')
    if raw is not None:
        goes_with = _text_list(raw, f'{base}.goes_with')
    return Product(
        id=product_id,
        name=_text(_required(entry, 'name', f'{base}.name'), f'{base}.name'),
        form=_text(_required(entry, 'form', f'{base}.form'), f'{base}.form'),
        price=_text(_required(entry, 'price', f'{base}.price'), f'{base}.price'),
        description=_text(
            _required(entry, 'description', f'{base}.description'),
            f'{base}.description',
        ),
        goes_with=goes_with,
    )


def _document(data: Any) -> KnowledgeBase:
    """Check the parsed document."""
    if not isinstance(data, dict):
        raise KnowledgeBaseError('the document is not a mapping', None)
    _known_keys(data, TOP_KEYS, '')
    disclaimer = None
    if data.get('disclaimer') is not None:
        disclaimer = _text(data['disclaimer'], 'disclaimer')
    raw_products = _required(data, 'products', 'products')
    if not isinstance(raw_products, list) or not raw_products:
        raise KnowledgeBaseError('products must be a non-empty list', 'products')
    known_ids: set[str] = set()
    products = [
        _product(entry, index, known_ids) for index, entry in enumerate(raw_products)
    ]
    for index, product in enumerate(products):
        field = f'products.{index}.goes_with'
        for reference in product.goes_with:
            if reference not in known_ids:
                raise KnowledgeBaseError(
                    f'{field} names the unknown product {reference}', field
                )
    return KnowledgeBase(
        company=_text(_required(data, 'company', 'company'), 'company'),
        language=_text(_required(data, 'language', 'language'), 'language'),
        reply_rules=_text_list(
            _required(data, 'reply_rules', 'reply_rules'), 'reply_rules'
        ),
        forbidden_claims=_text_list(
            _required(data, 'forbidden_claims', 'forbidden_claims'), 'forbidden_claims'
        ),
        products=products,
        disclaimer=disclaimer,
    )


# === Loading ===


def _read(path: Path) -> Any:
    """Read the file and parse YAML."""
    return yaml.safe_load(path.read_text(encoding='utf-8'))


async def load_knowledge_base(path: Path) -> KnowledgeBase:
    """Load one knowledge base file."""
    try:
        data = await asyncio.to_thread(_read, path)
    except OSError as error:
        raise KnowledgeBaseError(f'cannot read {path}: {error}', None) from error
    except yaml.YAMLError as error:
        raise KnowledgeBaseError(f'invalid YAML in {path}: {error}', None) from error
    return _document(data)
