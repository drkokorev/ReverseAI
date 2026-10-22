"""Run scenarios against a live base URL (package-side wrapper over `standalone`)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from reverseai.oracle import standalone
from reverseai.oracle.model import Scenario, ScenarioResult, StepFailure

__all__ = ["ScenarioResult", "StepFailure", "run_scenarios"]


class _Throttled:
    """httpx-like client that starts requests at least `delay_s` seconds apart."""

    def __init__(self, client: httpx.Client, delay_s: float) -> None:
        self._client = client
        self._delay_s = delay_s
        self._last: float | None = None

    def request(self, *args: Any, **kwargs: Any) -> httpx.Response:
        if self._last is not None:
            wait = self._last + self._delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        self._last = time.monotonic()
        return self._client.request(*args, **kwargs)


def run_scenarios(
    scenarios: list[Scenario],
    base_url: str,
    *,
    reset: Callable[[], None] | None = None,
    client: httpx.Client | None = None,
    delay_s: float = 0.0,
) -> list[ScenarioResult]:
    """Run each scenario in order, calling `reset()` before each one when given.

    With `delay_s` > 0, requests start at least `delay_s` seconds apart (rate limit toward a
    target: 0.5 means at most 2 requests per second).
    """
    own_client = client is None
    http = client or httpx.Client(trust_env=False, timeout=standalone.REQUEST_TIMEOUT_S)
    sender: Any = _Throttled(http, delay_s) if delay_s > 0 else http
    try:
        results = []
        for scenario in scenarios:
            if reset is not None:
                reset()
            raw = standalone.run_scenario(base_url, scenario.model_dump(), sender)
            results.append(ScenarioResult.model_validate(raw))
        return results
    finally:
        if own_client:
            http.close()
