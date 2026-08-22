"""Model access layer.

Talks to a model through the Ollama HTTP API, which any local Ollama instance
(or any OpenAI-compatible server) can provide. The only thing the benchmark
needs is a *streaming* chat completion with token counts so it can measure
latency and throughput.

The client is intentionally transport-agnostic: callers pass an object with a
``.post(url, json=...) -> Response`` method. In production that is a
``requests.Session``; in tests it is a fake. This keeps the HTTP layer out of
the unit tests.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class HTTPClient(Protocol):
    """A minimal subset of ``requests.Session`` used by the client."""

    def post(self, url: str, json: dict[str, Any], timeout: float, stream: bool = False) -> Any:
        ...


@dataclass
class CompletionRequest:
    """A single chat completion request."""

    model: str
    prompt: str
    system: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    """A completed chat turn plus the metrics the benchmark needs."""

    text: str
    prompt_tokens: int
    output_tokens: int
    time_to_first_token: float
    total_time: float

    def tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


class ModelError(RuntimeError):
    """Raised when the model server is unreachable or returns an error."""


class OllamaClient:
    """Streams chat completions from an Ollama (or OpenAI-compatible) server."""

    def __init__(self, base_url: str, http: HTTPClient | None = None, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if http is None:
            import requests

            self.http = requests.Session()
        else:
            self.http = http

    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Send one request and stream the response, timing the turn."""
        url = f"{self.base_url}/api/chat"
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        if request.options:
            payload["options"] = request.options

        start = time.monotonic()
        response = self.http.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        text = ""
        prompt_tokens = 0
        output_tokens = 0
        time_to_first_token = 0.0
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise ModelError(str(chunk["error"]))
            if time_to_first_token == 0.0 and chunk.get("message", {}).get("content"):
                time_to_first_token = time.monotonic() - start
            message = chunk.get("message", {})
            text += message.get("content", "")
            if chunk.get("done"):
                prompt_tokens = chunk.get("prompt_eval_count", prompt_tokens)
                output_tokens = chunk.get("eval_count", output_tokens)

        total_time = time.monotonic() - start
        return CompletionResult(
            text=text,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            time_to_first_token=time_to_first_token,
            total_time=total_time,
        )
