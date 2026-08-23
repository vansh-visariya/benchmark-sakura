"""Tests for the multi-turn tool-calling chat path in models.py."""
import json

import pytest

from models import OllamaClient, ModelError, ToolCall, ChatTurnResult, BASH_TOOL_SPEC


def _line(obj: dict) -> str:
    return json.dumps(obj)


class _FakeResponse:
    def __init__(self, lines, status: int = 200):
        self._lines = lines
        self.status_code = status

    def iter_lines(self, decode_unicode: bool = True):
        return iter(self._lines)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class _FakeSession:
    def __init__(self, lines):
        self.lines = lines
        self.last_url = None
        self.last_payload = None

    def post(self, url, json=None, timeout=..., stream=False):
        self.last_url = url
        self.last_payload = json
        return _FakeResponse(self.lines)


def test_chat_parses_tool_calls_and_counts():
    lines = [
        _line({"message": {"content": "Looking at the files."}}),
        _line({
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "bash", "arguments": {"command": "echo hello"}}}
                ],
            }
        }),
        _line({"done": True, "prompt_eval_count": 8, "eval_count": 3}),
    ]
    session = _FakeSession(lines)
    client = OllamaClient("http://x", http=session)
    result = client.chat([{"role": "user", "content": "hi"}], model="m", tools=[BASH_TOOL_SPEC])
    assert result.text == "Looking at the files."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "bash"
    assert result.tool_calls[0].arguments == {"command": "echo hello"}
    assert result.prompt_tokens == 8
    assert result.output_tokens == 3
    assert result.time_to_first_token > 0
    assert result.total_time >= 0
    # tools were sent through
    assert session.last_payload["tools"] == [BASH_TOOL_SPEC]
    assert session.last_payload["model"] == "m"


def test_chat_string_arguments_are_parsed():
    lines = [
        _line({
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "bash", "arguments": '{"command": "ls -la"}'}}
                ],
            }
        }),
        _line({"done": True, "prompt_eval_count": 4, "eval_count": 1}),
    ]
    client = OllamaClient("http://x", http=_FakeSession(lines))
    result = client.chat([{"role": "user", "content": "hi"}], model="m", tools=[])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].arguments == {"command": "ls -la"}


def test_chat_no_tool_calls():
    lines = [
        _line({"message": {"content": "All done!"}}),
        _line({"done": True, "prompt_eval_count": 2, "eval_count": 3}),
    ]
    client = OllamaClient("http://x", http=_FakeSession(lines))
    result = client.chat([{"role": "user", "content": "hi"}], model="m", tools=[])
    assert result.tool_calls == []
    assert result.text == "All done!"


def test_chat_malformed_json_raises_model_error():
    client = OllamaClient("http://x", http=_FakeSession(["not-json", '{"done": true}']))
    with pytest.raises(ModelError):
        client.chat([{"role": "user", "content": "hi"}], model="m", tools=[])


def test_chat_server_error_raises_model_error():
    client = OllamaClient("http://x", http=_FakeSession([_line({"error": "oom"})]))
    with pytest.raises(ModelError):
        client.chat([{"role": "user", "content": "hi"}], model="m", tools=[])


def test_chat_turn_result_is_built():
    # sanity: dataclass shape matches what agent.py expects
    tr = ChatTurnResult(text="t", tool_calls=[ToolCall(name="bash", arguments={"command": "x"})])
    assert tr.text == "t"
    assert tr.tool_calls[0].name == "bash"
