"""Checks of the model output."""

from reply_assistant.knowledge_base import KnowledgeBase
from reply_assistant.suggestion import ModelOutput

# === Error ===


class CheckError(Exception):
    """A check rejected the output."""

    def __init__(self, message: str, check: str) -> None:
        """Keep the message and the check."""
        super().__init__(message)
        self.check = check


# === Comparison ===


def _comparable(text: str) -> str:
    """Lowercase and replace separators."""
    return ''.join(
        character if character.isalpha() or character.isdigit() else ' '
        for character in text.lower()
    )


# === Checks ===


def check_product_exists(output: ModelOutput, kb: KnowledgeBase) -> None:
    """Check the upsell product id."""
    product_id = output.upsell_product_id
    if product_id is None:
        return
    for product in kb.products:
        if product.id == product_id:
            return
    raise CheckError(
        f'the product {product_id} is not in the knowledge base', 'product_exists'
    )


def check_no_forbidden_claim(output: ModelOutput, kb: KnowledgeBase) -> None:
    """Check the forbidden claim stems."""
    fields = {
        'customer_reply': output.customer_reply,
        'upsell_hint': output.upsell_hint,
    }
    for name, value in fields.items():
        padded = f' {_comparable(value)} '
        for stem in kb.forbidden_claims:
            if _comparable(stem) in padded:
                raise CheckError(
                    f'the field {name} contains the forbidden stem {stem.strip()}',
                    'no_forbidden_claim',
                )


# === Disclaimer ===


def append_disclaimer(reply: str, kb: KnowledgeBase) -> str:
    """Append the kb disclaimer."""
    if kb.disclaimer is None:
        return reply
    return f'{reply}\n\n{kb.disclaimer}'
