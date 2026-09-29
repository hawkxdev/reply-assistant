"""Entry point tests."""

import pytest
import uvicorn

from reply_assistant import __main__


def test_main_starts_local_server(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(target: str, **options: object) -> None:
        """Record server start."""
        calls.append((target, options))

    monkeypatch.setattr(uvicorn, 'run', fake_run)

    __main__.main()

    assert calls == [
        (
            'reply_assistant.app:create_app',
            {'factory': True, 'host': '127.0.0.1', 'port': 8000},
        )
    ]
