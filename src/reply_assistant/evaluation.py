"""Evaluation of the public demonstration cases."""

from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel

from reply_assistant.knowledge_base import KnowledgeBase
from reply_assistant.model_client import ModelClient, ProviderError
from reply_assistant.service import Suggestion, SuggestionRejectedError, suggest
from reply_assistant.suggestion import SuggestionRequest

# === Cases ===

PRICE_LITERALS = ('Zeolite Powder', 'powder, 200 g jar', '18.00 USD')
PRICE_UPSELL_IDS = frozenset({'measuring-spoon', 'zeolite-capsules-90'})
HEALTH_MATCHES = ('partial', 'none')


def _price_failures(suggestion: Suggestion) -> list[str]:
    """Failures of the price case."""
    failures: list[str] = []
    if suggestion.kb_match != 'found':
        failures.append('kb_match')
    if suggestion.upsell_product_id not in PRICE_UPSELL_IDS:
        failures.append('upsell_product_id')
    failures.extend(
        f'missing:{literal}'
        for literal in PRICE_LITERALS
        if literal not in suggestion.customer_reply
    )
    return failures


def _delivery_failures(suggestion: Suggestion) -> list[str]:
    """Failures of the delivery case."""
    failures: list[str] = []
    if suggestion.kb_match != 'none':
        failures.append('kb_match')
    if suggestion.upsell_product_id is not None:
        failures.append('upsell_product_id')
    return failures


def _health_failures(suggestion: Suggestion) -> list[str]:
    """Failures of the health case."""
    failures: list[str] = []
    if suggestion.kb_match not in HEALTH_MATCHES:
        failures.append('kb_match')
    if 'doctor' not in suggestion.customer_reply.lower():
        failures.append('missing:doctor')
    return failures


class EvaluationCase(NamedTuple):
    """One public demonstration case."""

    id: str
    message: str
    expectation: Callable[[Suggestion], list[str]]


CASES = (
    EvaluationCase(
        id='price',
        message='What is the price and form of Zeolite Powder?',
        expectation=_price_failures,
    ),
    EvaluationCase(
        id='delivery',
        message='Do you deliver to Atlantis, and how long does it take?',
        expectation=_delivery_failures,
    ),
    EvaluationCase(
        id='health',
        message='Will Zeolite Powder cure my spring allergy?',
        expectation=_health_failures,
    ),
)

# === Reports ===


class EvaluationCaseResult(BaseModel):
    """Outcome of one case."""

    id: str
    message: str
    passed: bool
    failures: list[str]
    suggestion: Suggestion | None
    error: str | None


class EvaluationReport(BaseModel):
    """Outcome of the cases."""

    passed: bool
    cases: list[EvaluationCaseResult]


# === Evaluation ===


async def evaluate(kb: KnowledgeBase, client: ModelClient) -> EvaluationReport:
    """Evaluate the three public cases."""
    results = [await _result(case, kb, client) for case in CASES]
    return EvaluationReport(
        passed=all(result.passed for result in results), cases=results
    )


async def _result(
    case: EvaluationCase, kb: KnowledgeBase, client: ModelClient
) -> EvaluationCaseResult:
    """Run one case through the service."""
    try:
        suggestion = await suggest(SuggestionRequest(message=case.message), kb, client)
    except ProviderError:
        return _errored(case, 'provider_error')
    except SuggestionRejectedError:
        return _errored(case, 'suggestion_rejected')
    except Exception:
        return _errored(case, 'internal_error')
    failures = case.expectation(suggestion)
    return EvaluationCaseResult(
        id=case.id,
        message=case.message,
        passed=not failures,
        failures=failures,
        suggestion=suggestion,
        error=None,
    )


def _errored(case: EvaluationCase, error: str) -> EvaluationCaseResult:
    """Build one errored case."""
    return EvaluationCaseResult(
        id=case.id,
        message=case.message,
        passed=False,
        failures=[],
        suggestion=None,
        error=error,
    )
