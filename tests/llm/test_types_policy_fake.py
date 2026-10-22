import pytest

from reverseai.llm.policy import DataPolicy, PolicyViolation
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest, LLMResponse, Message, ProviderError, Usage


def req(text: str = "hello world!", system: str | None = None) -> LLMRequest:
    return LLMRequest(
        model="m1", system=system, messages=[Message(role="user", content=text)], max_tokens=64
    )


def test_fake_script_order_and_errors():
    p = FakeProvider(script=["a", ProviderError("busy", retryable=True, status=429), "b"])
    assert p.complete(req()).text == "a"
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is True and ei.value.status == 429
    assert p.complete(req()).text == "b" and len(p.requests) == 3


def test_fake_responder():
    p = FakeProvider(name="fk", responder=lambda r: r.messages[-1].content.upper())
    resp = p.complete(req("abcdefgh"))
    assert isinstance(resp, LLMResponse)
    assert resp.text == "ABCDEFGH"
    assert resp.provider == "fk" and resp.model == "m1"
    assert resp.usage == Usage(input_tokens=2, output_tokens=2)
    assert resp.cost_usd == 0.0


def test_fake_usage_counts_system_and_messages():
    p = FakeProvider(responder=lambda r: "x" * 12)
    resp = p.complete(req("a" * 8, system="b" * 8))
    assert resp.usage.input_tokens == 4 and resp.usage.output_tokens == 3


def test_fake_script_then_responder_and_exhaustion():
    p = FakeProvider(script=["first"], responder=lambda r: "later")
    assert [p.complete(req()).text for _ in range(2)] == ["first", "later"]
    q = FakeProvider(script=["only"])
    q.complete(req())
    with pytest.raises(ProviderError, match="fake script exhausted") as ei:
        q.complete(req())
    assert ei.value.retryable is False and ei.value.status is None


def test_fake_no_script_no_responder_raises():
    with pytest.raises(ProviderError):
        FakeProvider().complete(req())


def test_default_policy_excludes_cn():
    assert "cn" not in DataPolicy().allowed_jurisdictions
    assert DataPolicy().allowed_jurisdictions == {"us", "eu", "self"}


def test_policy_instances_do_not_share_state():
    a, b = DataPolicy(), DataPolicy()
    a.allowed_jurisdictions.add("cn")
    assert "cn" not in b.allowed_jurisdictions


def test_policy_violation_is_exception():
    assert issubclass(PolicyViolation, Exception)
