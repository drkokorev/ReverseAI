import json

import pytest

from reverseai.config import load_settings
from reverseai.llm.gateway import Gateway, GatewayError, cost_usd
from reverseai.llm.policy import DataPolicy, PolicyViolation
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMResponse, Message, ProviderError, Usage
from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import Zone

MSGS = [Message(role="user", content="secret prompt")]


def make(tmp_path, providers, **kw):
    settings = load_settings()
    ledger = Ledger(tmp_path / "ledger.jsonl")
    sleeps: list[float] = []
    gw = Gateway(settings, providers, ledger, sleep=sleeps.append, **kw)
    return gw, ledger, sleeps


def call(gw, role="executor", policy=None, messages=MSGS):
    return gw.complete(
        role,
        messages,
        system="sys",
        policy=policy or DataPolicy(),
        zone=Zone.CLEAN,
        actor="tester",
    )


def busy():
    return ProviderError("busy", retryable=True, status=429)


def test_policy_filters_cn_models(tmp_path):
    gw, ledger, _ = make(
        tmp_path, {"deepseek": FakeProvider("deepseek"), "zai": FakeProvider("zai")}
    )
    with pytest.raises(PolicyViolation):
        call(gw)
    assert ledger.events()[-1].type == "llm.error"
    # Allowing cn explicitly makes the same providers usable.
    gw2, _, _ = make(
        tmp_path / "b",
        {"deepseek": FakeProvider("deepseek", responder=lambda r: "ok")},
    )
    resp = call(
        gw2, policy=DataPolicy(allowed_jurisdictions={"us", "eu", "self", "cn"})
    )
    assert resp.model == "deepseek-v4-pro"


def test_candidates_without_built_provider_are_skipped(tmp_path):
    gw, _, _ = make(
        tmp_path, {"openai": FakeProvider("openai", responder=lambda r: "ok")}
    )
    assert call(gw).model == "gpt-6.1-sol"


def test_fallback_after_retryable_exhaustion(tmp_path):
    sonnet = FakeProvider("anthropic", script=[busy(), busy(), busy()])
    gpt = FakeProvider("openai", script=["ok"])
    gw, ledger, sleeps = make(tmp_path, {"anthropic": sonnet, "openai": gpt})
    resp = call(gw)
    assert (
        resp.text == "ok" and resp.model == "gpt-6.1-sol" and resp.provider == "openai"
    )
    assert len(sonnet.requests) == 3
    assert sleeps == [1, 2]
    assert ledger.events()[-1].payload["attempts"] == 4


def test_non_retryable_goes_to_next_candidate_without_sleep(tmp_path):
    sonnet = FakeProvider(
        "anthropic", script=[ProviderError("bad", retryable=False, status=400)]
    )
    gpt = FakeProvider("openai", script=["ok"])
    gw, _, sleeps = make(tmp_path, {"anthropic": sonnet, "openai": gpt})
    assert call(gw).text == "ok"
    assert len(sonnet.requests) == 1 and sleeps == []


def test_all_fail_raises_gateway_error_and_logs_error_event(tmp_path):
    err = ProviderError("down", retryable=False, status=500)
    gw, ledger, _ = make(
        tmp_path,
        {
            "anthropic": FakeProvider("anthropic", script=[err]),
            "openai": FakeProvider("openai", script=[err]),
        },
    )
    with pytest.raises(GatewayError):
        call(gw)
    event = ledger.events()[-1]
    assert event.type == "llm.error"
    assert event.payload["role"] == "executor"
    assert event.payload["tried_models"] == ["claude-sonnet-5-5", "gpt-6.1-sol"]
    assert len(event.payload["errors"]) == 2
    assert "secret prompt" not in ledger.path.read_text()


def test_unknown_role(tmp_path):
    gw, _, _ = make(tmp_path, {"anthropic": FakeProvider("anthropic")})
    with pytest.raises(GatewayError):
        call(gw, role="nope")


def test_cost_usd_formula():
    settings = load_settings()
    model = settings.models["claude-sonnet-5-5"]
    usage = Usage(
        input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=500_000
    )
    assert cost_usd(model, usage) == pytest.approx(0.5 * 2 + 0.5 * 0.10 + 10)


def test_cost_accounting(tmp_path):
    class Big(FakeProvider):
        def complete(self, req):
            return LLMResponse("x", req.model, self.name, Usage(1_000_000, 0))

    gw, ledger, _ = make(tmp_path, {"anthropic": Big("anthropic")})
    resp = call(gw)
    assert resp.cost_usd == 2.0
    summary = gw.costs()
    assert summary.by_role["executor"] == 2.0
    assert summary.by_model["claude-sonnet-5-5"] == 2.0
    assert summary.total_usd == 2.0 and summary.calls == 1
    assert ledger.events()[-1].payload["cost_usd"] == 2.0


def test_ledger_has_hash_not_prompt(tmp_path):
    gw, ledger, _ = make(
        tmp_path,
        {"anthropic": FakeProvider("anthropic", responder=lambda r: "reply text")},
    )
    call(gw)
    event = ledger.events()[-1]
    assert (
        event.type == "llm.call" and event.zone == "clean" and event.actor == "tester"
    )
    p = event.payload
    assert len(p["prompt_sha256"]) == 64 and len(p["response_sha256"]) == 64
    assert p["role"] == "executor" and p["model"] == "claude-sonnet-5-5"
    assert p["provider"] == "anthropic" and p["attempts"] == 1
    assert set(p["usage"]) == {"input_tokens", "output_tokens", "cached_input_tokens"}
    raw = ledger.path.read_text()
    assert "secret prompt" not in raw and "reply text" not in raw


def test_transcript_written_on_success_only(tmp_path):
    tdir = tmp_path / "transcripts"
    err = ProviderError("down", retryable=False)
    gw, ledger, _ = make(
        tmp_path,
        {"anthropic": FakeProvider("anthropic", script=[err, "fine"])},
        transcripts_dir=tdir,
    )
    with pytest.raises(GatewayError):
        call(gw)
    assert not tdir.exists() or not list(tdir.iterdir())
    call(gw)
    event = ledger.events()[-1]
    data = json.loads((tdir / f"{event.seq}.json").read_text())
    assert data["request"]["messages"] == [{"role": "user", "content": "secret prompt"}]
    assert (
        data["request"]["system"] == "sys"
        and data["request"]["model"] == "claude-sonnet-5-5"
    )
    assert data["request"]["max_tokens"] == 8192
    assert data["response"]["text"] == "fine"
    assert data["response"]["cost_usd"] == event.payload["cost_usd"]
    assert (
        data["role"] == "executor"
        and data["zone"] == "clean"
        and data["actor"] == "tester"
    )
    assert len(list(tdir.iterdir())) == 1
