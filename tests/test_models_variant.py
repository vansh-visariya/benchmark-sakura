"""Tests for model-variant metadata (quantization) capture and propagation."""
import pytest

from models import ModelVariant, OllamaClient
from runner import Runner, RunResult


class _ShowResponse:
    def __init__(self, body, status: int = 200):
        self._body = body
        self.status_code = status

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class _ShowSession:
    """Serves /api/show from canned bodies keyed by model tag."""

    def __init__(self, bodies):
        self._bodies = bodies
        self.last_url = None

    def post(self, url, json=None, timeout=..., stream=False):
        self.last_url = url
        model = (json or {}).get("model", "")
        if model in self._bodies:
            return _ShowResponse(self._bodies[model])
        return _ShowResponse({}, status=404)


def test_show_parses_ollama_details():
    session = _ShowSession({
        "qwen2.5:7b": {
            "details": {
                "quantization_level": "Q4_K_M",
                "parameter_size": "7.6B",
                "family": "qwen2",
            }
        }
    })
    client = OllamaClient("http://x", http=session)
    variant = client.show("qwen2.5:7b")
    assert variant == ModelVariant(
        quantization="Q4_K_M", parameter_size="7.6B", family="qwen2"
    )
    assert session.last_url == "http://x/api/show"


def test_show_degrades_when_model_unknown():
    client = OllamaClient("http://x", http=_ShowSession({}))
    variant = client.show("nope:latest")
    assert variant == ModelVariant(quantization=None, parameter_size=None, family=None)


def test_show_swallows_transport_errors():
    class _BoomSession(_ShowSession):
        def post(self, url, json=None, timeout=..., stream=False):
            raise ConnectionError("server down")

    client = OllamaClient("http://x", http=_BoomSession({}))
    assert client.show("m") == ModelVariant()


def _runner_with_variant(config) -> Runner:
    runner = Runner.__new__(Runner)
    runner.manifest = None
    runner.client = OllamaClient("http://x", http=_ShowSession({}))
    runner.executor = None
    runner.hardware = None
    runner.config = config
    return runner


def test_resolve_variant_uses_show_result(monkeypatch):
    from config import Config

    runner = _runner_with_variant(Config())
    monkeypatch.setattr(runner.client, "show", lambda m: ModelVariant(quantization="Q8_0"))
    assert runner.resolve_variant("any-model").quantization == "Q8_0"


def test_resolve_variant_override_wins(monkeypatch):
    from config import Config

    runner = _runner_with_variant(Config())
    runner.config.model_variant = "Q4_K_M/7.6B/qwen2"
    monkeypatch.setattr(
        runner.client, "show", lambda m: ModelVariant(quantization="Q8_0")
    )
    variant = runner.resolve_variant("any-model")
    assert variant.quantization == "Q4_K_M"
    assert variant.parameter_size == "7.6B"
    assert variant.family == "qwen2"


def test_runresult_serializes_nonempty_variant_only():
    result = RunResult(
        model="m",
        version="0.2.0",
        hardware={},
        metrics={},
        task_results=[],
        model_variant=ModelVariant(quantization="Q4_K_M"),
    )
    payload = result.to_dict()
    assert payload["model_variant"] == {"quantization": "Q4_K_M"}

    empty = RunResult(
        model="m",
        version="0.2.0",
        hardware={},
        metrics={},
        task_results=[],
        model_variant=ModelVariant(),
    )
    assert "model_variant" not in empty.to_dict()