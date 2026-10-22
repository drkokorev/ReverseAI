import json
from pathlib import Path

import pytest

from reverseai.config import load_settings
from reverseai.llm.gateway import Gateway
from reverseai.llm.jsonout import LLMOutputError
from reverseai.llm.policy import DataPolicy
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest
from reverseai.observe.bundle import ObservationBundle
from reverseai.observe.contracts import Endpoint
from reverseai.observe.explorer import PageObservation
from reverseai.provenance.ledger import Ledger
from reverseai.spec.builder import build_spec, critique_spec
from reverseai.spec.model import AnalystDraft, BehaviorSpec

FIXTURES = Path(__file__).parent.parent / "fixtures" / "llm"
ANALYST_JSON = (FIXTURES / "analyst_spec.json").read_text(encoding="utf-8")
CRITIC_JSON = (FIXTURES / "critic.json").read_text(encoding="utf-8")


def make_bundle() -> ObservationBundle:
    page = PageObservation(
        url="http://127.0.0.1:8000/",
        title="Board",
        links=[],
        forms=[],
        buttons=["Add"],
        text_excerpt="hello",
        screenshot_ref=None,
    )
    post = Endpoint(
        method="POST",
        path_template="/api/tasks",
        statuses=[201, 422],
        request_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        response_schemas={
            201: {"type": "object", "properties": {"id": {"type": "integer"}}},
            422: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        exchange_ids=["e1", "e2"],
    )
    get = Endpoint(
        method="GET",
        path_template="/api/tasks/{id}",
        statuses=[200, 404],
        request_schema=None,
        response_schemas={200: {"type": "object"}, 404: {}},
        exchange_ids=["e3"],
    )
    return ObservationBundle(pages=[page], endpoints=[post, get], probe_exchanges=[], docs=[])


def make_gateway(tmp_path, responder):
    fake = FakeProvider(name="anthropic", responder=responder)
    gw = Gateway(load_settings(), {"anthropic": fake}, Ledger(tmp_path / "ledger.jsonl"))
    return gw, fake


def by_role(analyst, critic):
    def responder(req: LLMRequest) -> str:
        system = req.system or ""
        if system.startswith("[role:analyst]"):
            return analyst(req) if callable(analyst) else analyst
        if system.startswith("[role:spec_critic]"):
            return critic(req) if callable(critic) else critic
        raise AssertionError(f"unexpected system prompt: {system[:40]!r}")

    return responder


def roles(fake: FakeProvider) -> list[str]:
    return [(r.system or "").split("]")[0].removeprefix("[role:") for r in fake.requests]


def test_fixtures_are_valid_analyst_and_critic_outputs():
    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    assert draft.features and draft.rules and draft.entities and draft.gaps
    codes = " ".join(i.description for i in draft.rules)
    for code in ("title_required", "title_too_long", "invalid_priority", "duplicate", "not_found"):
        assert code in codes
    assert isinstance(json.loads(CRITIC_JSON)["issues"], list)


def test_build_spec_merges_llm_and_api(tmp_path):
    gw, fake = make_gateway(tmp_path, by_role(ANALYST_JSON, CRITIC_JSON))
    bundle = make_bundle()

    spec = build_spec(gw, bundle, product_name="Tasklet", policy=DataPolicy())

    assert spec.product_name == "Tasklet"
    assert spec.version == 1
    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    assert spec.summary == draft.summary
    assert [f.id for f in spec.features] == [f.id for f in draft.features]
    assert {(a.method, a.path) for a in spec.api} == {
        ("POST", "/api/tasks"),
        ("GET", "/api/tasks/{id}"),
    }
    post = next(a for a in spec.api if a.method == "POST")
    assert post.responses == bundle.endpoints[0].response_schemas
    assert all(isinstance(status, int) for status in post.responses)
    assert post.request_schema == bundle.endpoints[0].request_schema
    assert post.description == ""
    # draft gaps are kept and the critic's issues are appended, prefixed
    assert spec.gaps[: len(draft.gaps)] == draft.gaps
    for issue in json.loads(CRITIC_JSON)["issues"]:
        assert f"critic: {issue}" in spec.gaps
    # analyst, critic, one revision by the analyst; no second critic call
    assert roles(fake) == ["analyst", "spec_critic", "analyst"]


def test_build_spec_prompts_carry_bundle_product_and_rules(tmp_path):
    gw, fake = make_gateway(tmp_path, by_role(ANALYST_JSON, CRITIC_JSON))

    build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    first, critic_req, revision = fake.requests
    assert "Tasklet" in first.messages[0].content
    assert "POST /api/tasks" in first.messages[0].content
    assert "http://127.0.0.1:8000/" in first.messages[0].content
    system = first.system.lower()
    for phrase in ("own words", "never copy", "brand", "gap", "evidence"):
        assert phrase in system
    assert "Tasklet" in critic_req.messages[0].content
    assert "POST /api/tasks" in critic_req.messages[0].content
    # revision sees the previous draft and the critic issues
    assert [m.role for m in revision.messages] == ["user", "assistant", "user"]
    assert json.loads(revision.messages[1].content)["summary"]
    for issue in json.loads(CRITIC_JSON)["issues"]:
        assert issue in revision.messages[2].content


def test_build_spec_uses_revised_draft(tmp_path):
    calls = {"analyst": 0}
    revised = json.loads(ANALYST_JSON)
    revised["summary"] = "revised summary"

    def analyst(req):
        calls["analyst"] += 1
        return ANALYST_JSON if calls["analyst"] == 1 else json.dumps(revised)

    gw, _ = make_gateway(tmp_path, by_role(analyst, '{"issues": ["critic issue A"]}'))

    spec = build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    assert spec.summary == "revised summary"
    assert "critic: critic issue A" in spec.gaps


def test_critic_prompt_forbids_quoting_observed_text(tmp_path):
    gw, fake = make_gateway(tmp_path, by_role(ANALYST_JSON, CRITIC_JSON))

    build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    critic_system = fake.requests[1].system
    assert "never quote observed text, wording, code or names in an issue" in critic_system
    assert "item id or field name" in critic_system


def test_build_spec_falls_back_to_first_draft_when_revision_is_invalid(tmp_path):
    calls = {"analyst": 0}

    def analyst(req):
        calls["analyst"] += 1
        return ANALYST_JSON if calls["analyst"] == 1 else "not json"

    gw, fake = make_gateway(tmp_path, by_role(analyst, '{"issues": ["critic issue A"]}'))

    spec = build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    assert spec.summary == draft.summary
    assert spec.gaps == [*draft.gaps, "critic: critic issue A"]
    # first draft, critic, revision attempt + its repair retry
    assert roles(fake) == ["analyst", "spec_critic", "analyst", "analyst"]


def test_build_spec_without_issues_skips_revision(tmp_path):
    gw, fake = make_gateway(tmp_path, by_role(ANALYST_JSON, '{"issues": []}'))

    spec = build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    assert roles(fake) == ["analyst", "spec_critic"]
    assert spec.gaps == AnalystDraft.model_validate_json(ANALYST_JSON).gaps


def test_build_spec_invalid_json_twice_raises(tmp_path):
    gw, fake = make_gateway(tmp_path, by_role("not json at all", CRITIC_JSON))

    with pytest.raises(LLMOutputError):
        build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    assert roles(fake) == ["analyst", "analyst"]


def test_build_spec_draft_missing_fields_raises(tmp_path):
    gw, _ = make_gateway(tmp_path, by_role('{"summary": "only"}', CRITIC_JSON))

    with pytest.raises(LLMOutputError):
        build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())


def test_critique_spec_returns_issues_and_rejects_bad_shape(tmp_path):
    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    spec = BehaviorSpec(
        product_name="Tasklet",
        summary=draft.summary,
        features=draft.features,
        entities=draft.entities,
        rules=draft.rules,
        api=[],
        gaps=[],
    )
    gw, _ = make_gateway(tmp_path, by_role(ANALYST_JSON, '{"issues": ["a", "  ", "b"]}'))
    assert critique_spec(gw, spec, make_bundle(), policy=DataPolicy()) == ["a", "b"]

    gw, _ = make_gateway(tmp_path, by_role(ANALYST_JSON, '{"problems": ["a"]}'))
    with pytest.raises(LLMOutputError):
        critique_spec(gw, spec, make_bundle(), policy=DataPolicy())


def test_llm_calls_are_logged_as_dirty_zone_with_actors(tmp_path):
    gw, _ = make_gateway(tmp_path, by_role(ANALYST_JSON, CRITIC_JSON))

    build_spec(gw, make_bundle(), product_name="Tasklet", policy=DataPolicy())

    events = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text().splitlines()
        if '"llm.call"' in line
    ]
    assert [(e["actor"], e["zone"]) for e in events] == [
        ("spec.analyst", "dirty"),
        ("spec.critic", "dirty"),
        ("spec.analyst", "dirty"),
    ]


def test_spec_sha256_is_stable_and_content_sensitive():
    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    kwargs = {
        "product_name": "Tasklet",
        "summary": draft.summary,
        "features": draft.features,
        "entities": draft.entities,
        "rules": draft.rules,
        "api": [],
        "gaps": [],
    }
    a, b = BehaviorSpec(**kwargs), BehaviorSpec(**kwargs)
    assert a.sha256() == b.sha256()
    assert len(a.sha256()) == 64
    b.gaps.append("x")
    assert a.sha256() != b.sha256()
    # round trip through JSON keeps the hash (int keys become strings and back)
    spec = BehaviorSpec(**kwargs)
    assert BehaviorSpec.model_validate_json(spec.model_dump_json()).sha256() == spec.sha256()
