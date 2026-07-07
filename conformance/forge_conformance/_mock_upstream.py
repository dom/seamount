"""Minimal OpenAI-compatible upstream for llm-forge conformance runs.

Serves ``POST /v1/chat/completions`` with a canned response so the llm-forge
positive-path conformance items (envelope handling, receipt signatures) can
run without a real provider or API key. Loopback-only by design.

Usage:
    python -m forge_conformance._mock_upstream --port 5109
    # then: LLM_FORGE_BASE_URL=http://127.0.0.1:5109/v1 llm-forge serve ...
"""
from __future__ import annotations

import argparse
from typing import Sequence

from flask import Flask, jsonify, request

CANNED_RESPONSE_TEXT = "conformance canned response"


def create_app() -> Flask:
    app = Flask("forge-conformance-mock-upstream")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "role": "mock-upstream"})

    @app.post("/v1/chat/completions")
    def chat_completions():
        body = request.get_json(force=True, silent=True) or {}
        return jsonify({
            "id": "chatcmpl-conformance-0001",
            "object": "chat.completion",
            "model": body.get("model", "conformance-mock-model"),
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": CANNED_RESPONSE_TEXT,
                    },
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        })

    return app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge_conformance._mock_upstream")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    # Skip slow reverse-DNS during werkzeug startup on macOS CI runners
    # (same rationale as the forges' serve subcommands).
    import socket as _socket
    _socket.getfqdn = lambda name="": name or "localhost"

    create_app().run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
