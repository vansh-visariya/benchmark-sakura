"""Submit benchmark results to the Sakura leaderboard."""
from __future__ import annotations

import json

from pathlib import Path

from config import Config
from runner import RunResult


class SubmitError(RuntimeError):
    """Raised when the leaderboard API rejects or cannot receive a submission."""


def submit_result(result: RunResult, config: Config) -> str:
    """POST a run result to the leaderboard API. Returns the submission URL."""
    return _post_payload(result.to_dict(), config)


def submit_file(path: Path, config: Config) -> str:
    """Submit a previously saved results JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _post_payload(payload, config)


def _post_payload(payload: dict, config: Config) -> str:
    import requests

    url = f"{config.database_url.rstrip('/')}/api/v1/submissions"
    response = requests.post(url, json=payload, timeout=config.database_timeout)
    if response.status_code >= 400:
        raise SubmitError(f"HTTP {response.status_code}: {response.text[:500]}")
    try:
        body = response.json()
    except json.JSONDecodeError:
        return url
    submission_id = body.get("id", "")
    view_url = body.get("url", url)
    if submission_id:
        return f"{view_url} (id: {submission_id})"
    return view_url
