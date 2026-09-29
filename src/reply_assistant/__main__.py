"""Command line entry point."""

import uvicorn


def main() -> None:
    """Run the local server."""
    uvicorn.run(
        'reply_assistant.app:create_app',
        factory=True,
        host='127.0.0.1',
        port=8000,
    )


if __name__ == '__main__':
    main()
