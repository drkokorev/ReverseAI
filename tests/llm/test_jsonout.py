import pytest
from pydantic import BaseModel

from reverseai.config import load_settings
from reverseai.llm.gateway import Gateway
from reverseai.llm.jsonout import LLMOutputError, complete_json, extract_json
from reverseai.llm.policy import DataPolicy
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import Message
from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import Zone


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json("  [1, 2]\n") == [1, 2]
    assert extract_json('Here:\n```json\n{"a": [1, 2]}\n```\nbye') == {"a": [1, 2]}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": 2}} hope it helps') == {"a": {"b": 2}}
    assert extract_json("Result: [1, 2, 3].") == [1, 2, 3]
    # A bad fenced block does not stop the search for a valid span.
    assert extract_json('```json\nnot json\n```\n{"ok": true}') == {"ok": True}
    for bad in ("no json here", "{broken", '{"a": }', ""):
        with pytest.raises(LLMOutputError):
            extract_json(bad)


def gateway(tmp_path, script):
    fake = FakeProvider("anthropic", script=script)
    gw = Gateway(load_settings(), {"anthropic": fake}, Ledger(tmp_path / "l.jsonl"))
    return gw, fake


def run(gw, model_cls=None):
    return complete_json(
        gw,
        "executor",
        [Message(role="user", content="give json")],
        model_cls=model_cls,
        system="sys",
        policy=DataPolicy(),
        zone=Zone.CLEAN,
        actor="tester",
    )


def test_complete_json_repairs_once(tmp_path):
    gw, fake = gateway(tmp_path, ["not json", '{"a":1}'])
    assert run(gw) == {"a": 1}
    repair = fake.requests[1].messages
    assert [m.role for m in repair] == ["user", "assistant", "user"]
    assert repair[1].content == "not json"
    assert repair[2].content.startswith("Your previous output was invalid: ")
    assert repair[2].content.endswith("Reply with valid JSON only.")
    assert fake.requests[1].system == "sys"


def test_complete_json_second_failure_raises(tmp_path):
    gw, fake = gateway(tmp_path, ["x", "y", "never used"])
    with pytest.raises(LLMOutputError):
        run(gw)
    assert len(fake.requests) == 2


def test_complete_json_no_retry_when_valid(tmp_path):
    gw, fake = gateway(tmp_path, ['{"a":1}'])
    assert run(gw) == {"a": 1} and len(fake.requests) == 1


class Item(BaseModel):
    name: str
    n: int


def test_complete_json_model_cls_validates_and_repairs(tmp_path):
    gw, fake = gateway(tmp_path, ['{"name": "x"}', '{"name": "x", "n": 3}'])
    result = run(gw, Item)
    assert isinstance(result, Item) and result == Item(name="x", n=3)
    assert "n" in fake.requests[1].messages[-1].content


def test_complete_json_model_cls_failure_raises(tmp_path):
    gw, _ = gateway(tmp_path, ['{"name": "x"}', '{"name": 1}'])
    with pytest.raises(LLMOutputError):
        run(gw, Item)


def test_extract_json_prefers_the_outermost_span_over_bracketed_prose():
    assert extract_json('Note [1]: {"a": 1}') == {"a": 1}
    assert extract_json('See [x] and {"a": [1]} done') == {"a": [1]}
    assert extract_json('Answer: [1, {"a": 2}]') == [1, {"a": 2}]
    assert extract_json('Note {x} then {"a": 1} ok') == {"a": 1}
    assert extract_json('Refs [1] [2]: {"edits": [], "done": true}') == {"edits": [], "done": True}


def test_extract_json_deep_nesting_is_an_output_error_not_a_crash():
    deep = "[" * 100_000 + "]" * 100_000
    with pytest.raises(LLMOutputError):
        extract_json(deep)
    with pytest.raises(LLMOutputError):
        extract_json("text " + deep + " text")
