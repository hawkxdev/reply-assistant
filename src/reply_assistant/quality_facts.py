"""Verified typed fact index."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import cast, get_args

from reply_assistant.knowledge_base import KnowledgeBase, Product
from reply_assistant.quality_corpus import (
    QualityInputError,
    _check_edges,
    _check_evidence,
    _check_fact_grounded,
    _check_fact_shape,
    _check_support,
)
from reply_assistant.quality_schema import Fact, Predicate, ProductFacts, Unit

# === Typed values ===


@dataclass(frozen=True)
class PriceValue:
    """Price with explicit currency."""

    value: Decimal
    currency: str


# === Index models ===


@dataclass(frozen=True)
class VerifiedProductFacts:
    """Typed facts of one product."""

    product_id: str
    profile_id: str
    quantity_role: str
    support: Mapping[str, str]
    edges: tuple[str, ...]
    price: PriceValue | None
    _counts: Mapping[str, tuple[int, str]]
    _texts: Mapping[str, str]

    def count(self, predicate: str) -> tuple[int, str] | None:
        """Read one typed count."""
        return self._counts.get(predicate)

    def text(self, predicate: str) -> str | None:
        """Read one exact text."""
        return self._texts.get(predicate)


@dataclass(frozen=True)
class VerifiedFactIndex:
    """Verified fact index."""

    products: Mapping[str, VerifiedProductFacts]


# === Fact verification ===

_RETAINED_FIELDS = frozenset({'name', 'form', 'description'})
_FORM_QUANTITY_PREDICATES = frozenset(
    {'package_quantity', 'form_quantity', 'batch_capacity', 'section_count'}
)
_PROFILE_COMPONENTS: dict[str, dict[str, str]] = {
    'F01': {'form_kind': 'powder', 'container': 'jar'},
    'F02': {'form_kind': 'capsules'},
    'F03': {'form_kind': 'paste', 'container': 'tube'},
    'F04': {'form_kind': 'spoon', 'material': 'steel'},
    'F05': {'form_kind': 'box', 'material': 'plastic'},
    'F06': {'form_kind': 'зерно', 'container': 'пачка'},
    'F07': {'form_kind': 'фильтры'},
    'F08': {'form_kind': 'жернова', 'material': 'сталь'},
}
_PROFILE_QUANTITY_PREDICATE: dict[str, str] = {
    'F01': 'package_quantity',
    'F02': 'package_quantity',
    'F03': 'package_quantity',
    'F04': 'form_quantity',
    'F05': 'section_count',
    'F06': 'package_quantity',
    'F07': 'package_quantity',
    'F08': 'batch_capacity',
}
_PROFILE_QUANTITY_ROLE: dict[str, str] = {
    'F01': 'package_quantity',
    'F02': 'package_quantity',
    'F03': 'package_quantity',
    'F04': 'unresolved',
    'F05': 'section_count',
    'F06': 'package_quantity',
    'F07': 'package_quantity',
    'F08': 'batch_capacity',
}
_TypedValue = PriceValue | tuple[int, str] | str


def _check_retention(fact: Fact, product: Product, location: str) -> None:
    """Check full source text."""
    if fact.predicate in _RETAINED_FIELDS and fact.value != getattr(
        product, fact.predicate
    ):
        raise QualityInputError('inconsistent_fact', location)


def _check_edge_binding(fact: Fact, product: Product, product_index: int) -> None:
    """Bind relation evidence pointers."""
    bound = {
        f'/products/{product_index}/goes_with/{edge_index}'
        for edge_index, target in enumerate(product.goes_with)
        if target == fact.value
    }
    for evidence in fact.evidence:
        if evidence.pointer not in bound:
            raise QualityInputError('invalid_evidence', evidence.pointer)


def _check_retained_presence(annotation: ProductFacts, location: str) -> None:
    """Require the retained predicates."""
    present = {fact.predicate for fact in annotation.facts}
    if not _RETAINED_FIELDS.issubset(present):
        raise QualityInputError('inconsistent_fact', location)


def _check_profile(annotation: ProductFacts, location: str) -> None:
    """Check the declared profile."""
    if annotation.quantity_role != _PROFILE_QUANTITY_ROLE[annotation.profile_id]:
        raise QualityInputError('inconsistent_fact', f'{location}.quantity_role')
    components = _PROFILE_COMPONENTS[annotation.profile_id]
    quantity = _PROFILE_QUANTITY_PREDICATE[annotation.profile_id]
    for fact in annotation.facts:
        expected = components.get(fact.predicate)
        if expected is not None and fact.value != expected:
            raise QualityInputError('inconsistent_fact', location)
        if fact.predicate in _FORM_QUANTITY_PREDICATES and fact.predicate != quantity:
            raise QualityInputError('inconsistent_fact', location)


def _typed_value(fact: Fact) -> _TypedValue:
    """Convert one fact value."""
    if fact.value_type == 'decimal':
        return PriceValue(value=Decimal(fact.value), currency=cast('Unit', fact.unit))
    if fact.value_type == 'integer':
        return (int(fact.value), cast('Unit', fact.unit))
    return fact.value


def _support_matrix(annotation: ProductFacts) -> dict[str, str]:
    """Build the support matrix."""
    statuses: dict[str, str] = {
        entry.predicate: entry.status for entry in annotation.predicate_support
    }
    fact_predicates = {fact.predicate for fact in annotation.facts}
    for predicate in get_args(Predicate):
        if predicate not in statuses:
            statuses[predicate] = (
                'supported' if predicate in fact_predicates else 'unresolved'
            )
    return statuses


def _verified_product(
    catalogue: KnowledgeBase,
    product_index: int,
    position: int,
    annotation: ProductFacts,
) -> VerifiedProductFacts:
    """Verify one annotation."""
    base = f'products.{position}'
    product = catalogue.products[product_index]
    # Step 1: check evidence, shape, grounding and retained text of every fact.
    for fact_index, fact in enumerate(annotation.facts):
        fact_location = f'{base}.facts.{fact_index}'
        for evidence in fact.evidence:
            _check_evidence(catalogue, evidence, product_index)
        if fact.predicate == 'goes_with':
            _check_edge_binding(fact, product, product_index)
        _check_fact_shape(fact, fact_location)
        _check_fact_grounded(fact, fact_location)
        _check_retention(fact, product, fact_location)
    # Step 2: check the complete directed edges and the support matrix.
    _check_edges(annotation, product.goes_with, f'{base}.facts')
    _check_support(annotation, product.goes_with)
    # Step 3: require every retained predicate of the source text.
    _check_retained_presence(annotation, f'{base}.facts')
    # Step 4: check the declared profile against the annotated components.
    _check_profile(annotation, base)
    # Step 5: build typed values and reject contradictory repeats.
    values: dict[str, _TypedValue] = {}
    for fact in annotation.facts:
        if fact.predicate == 'goes_with':
            continue
        typed = _typed_value(fact)
        if fact.predicate in values and values[fact.predicate] != typed:
            raise QualityInputError('inconsistent_fact', f'{base}.facts')
        values[fact.predicate] = typed
    raw_price = values.get('price')
    counts = {
        predicate: value
        for predicate, value in values.items()
        if isinstance(value, tuple)
    }
    texts = {
        predicate: value
        for predicate, value in values.items()
        if isinstance(value, str)
    }
    return VerifiedProductFacts(
        product_id=annotation.product_id,
        profile_id=annotation.profile_id,
        quantity_role=annotation.quantity_role,
        support=MappingProxyType(_support_matrix(annotation)),
        edges=tuple(product.goes_with),
        price=raw_price if isinstance(raw_price, PriceValue) else None,
        _counts=MappingProxyType(counts),
        _texts=MappingProxyType(texts),
    )


# === Index construction ===


def build_fact_index(
    catalogue: KnowledgeBase, product_facts: Sequence[ProductFacts]
) -> VerifiedFactIndex:
    """Build the verified index."""
    # Step 1: bind every annotation to one catalogue product.
    positions = {product.id: index for index, product in enumerate(catalogue.products)}
    seen: set[str] = set()
    bound: list[tuple[int, ProductFacts]] = []
    for position, annotation in enumerate(product_facts):
        if annotation.product_id not in positions:
            raise QualityInputError(
                'unknown_reference', f'products.{position}.product_id'
            )
        if annotation.product_id in seen:
            raise QualityInputError('duplicate_id', f'products.{position}.product_id')
        seen.add(annotation.product_id)
        bound.append((position, annotation))
    if seen != set(positions):
        raise QualityInputError('inconsistent_fact', 'products')
    # Step 2: verify every annotation against the catalogue.
    entries = {
        annotation.product_id: _verified_product(
            catalogue, positions[annotation.product_id], position, annotation
        )
        for position, annotation in bound
    }
    return VerifiedFactIndex(products=MappingProxyType(entries))
