"""Fake model client."""

from typing import Any

from reply_assistant.model_client import Completion, ModelClient, ProviderError, Usage


class FakeModelClient:
    """Scripted model replies."""

    def __init__(self, replies: list[str | ProviderError]) -> None:
        """Keep the scripted replies."""
        self.replies = list(replies)
        self.calls: list[tuple[list[dict[str, str]], dict[str, Any]]] = []

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return the next reply."""
        self.calls.append((messages, schema))
        reply = self.replies.pop(0)
        if isinstance(reply, ProviderError):
            raise reply
        return Completion(
            text=reply,
            usage=Usage(input_tokens=100, output_tokens=20, provider='fake'),
        )


_conforms: ModelClient = FakeModelClient([])
