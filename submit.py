"""Submit benchmark results to the Sakura leaderboard."""
from __future__ import annotations

import json

from config import Config
from runner import RunResult


class SubmitError(RuntimeError):
    """Raised when the leaderboard API rejects or cannot receive a submission."""


def submit_result(result: RunResult, config: Config) -> str:
    """POST a run result to the leaderboard API. Returns the submission URL."""
    import requests

    url = f"{config.database_url.rstrip('/')}/api/v1/submissions"
    payload = result.to_dict()
    response = requests.post(url, json=payload, timeout=config.database_timeout)
    if response.status_code >= 400:
        raise SubmitError(f"HTTP {response.status_code}: {response.text[:500]}")
    try:
        body = response.json()
    except json.JSONDecodeError:
        return url
    return body.get("url", url)
