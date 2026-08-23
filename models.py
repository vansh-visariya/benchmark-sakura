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
    think: bool = False
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


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any]


@dataclass
class ChatTurnResult:
    """One conversational turn, possibly containing tool calls."""

    text: str
    tool_calls: list[ToolCall]
    prompt_tokens: int = 0
    output_tokens: int = 0
    time_to_first_token: float = 0.0
    total_time: float = 0.0


BASH_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run a shell command in the task workspace (/workspace) and receive "
            "its stdout, stderr, and exit code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}


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
            "think": request.think,
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
            chunk = _parse_stream_line(line)
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

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatTurnResult:
        """One multi-turn chat exchange, optionally with tool definitions.

        Returns the assistant's text plus any tool calls it requested. Tool
        calls may arrive on any streamed chunk; they are accumulated in order.
        """
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        start = time.monotonic()
        response = self.http.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        text = ""
        tool_calls: list[ToolCall] = []
        prompt_tokens = 0
        output_tokens = 0
        time_to_first_token = 0.0
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            chunk = _parse_stream_line(line)
            if chunk.get("error"):
                raise ModelError(str(chunk["error"]))
            message = chunk.get("message", {})
            content = message.get("content", "")
            if content and time_to_first_token == 0.0:
                time_to_first_token = time.monotonic() - start
            text += content
            for raw_call in message.get("tool_calls") or []:
                function = raw_call.get("function") or {}
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except ValueError:
                        arguments = {}
                tool_calls.append(
                    ToolCall(
                        name=str(function.get("name", "")),
                        arguments=arguments if isinstance(arguments, dict) else {},
                    )
                )
            if chunk.get("done"):
                prompt_tokens = chunk.get("prompt_eval_count", prompt_tokens)
                output_tokens = chunk.get("eval_count", output_tokens)

        total_time = time.monotonic() - start
        return ChatTurnResult(
            text=text,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            time_to_first_token=time_to_first_token,
            total_time=total_time,
        )


def _parse_stream_line(line: str) -> dict[str, Any]:
    """Parse one SSE line from Ollama, raising :class:`ModelError` on bad JSON."""
    try:
        chunk = json.loads(line)
    except (ValueError, TypeError) as exc:
        raise ModelError(f"malformed stream data from model server: {exc}") from exc
    if not isinstance(chunk, dict):
        raise ModelError("malformed stream data from model server: expected a JSON object")
    return chunk
