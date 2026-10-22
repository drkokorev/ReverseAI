from reverseai.observe.bundle import ObservationBundle
from reverseai.observe.contracts import Endpoint
from reverseai.observe.explorer import FormField, FormInfo, PageObservation
from reverseai.observe.har import Exchange


def make_page(n: int = 1, text: str = "hello") -> PageObservation:
    return PageObservation(
        url=f"http://t/p{n}",
        title=f"Page {n}",
        links=[f"http://t/p{n + 1}"],
        forms=[
            FormInfo(
                action="http://t/",
                method="POST",
                fields=[
                    FormField(name="title", type="text", required=True, label="Title"),
                    FormField(name="priority", type="select", required=False, label=None),
                ],
            )
        ],
        buttons=["Add task"],
        text_excerpt=text,
        screenshot_ref="deadbeef" * 8,
    )


def make_endpoint() -> Endpoint:
    return Endpoint(
        method="POST",
        path_template="/api/tasks",
        statuses=[201, 422],
        request_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["title"],
        },
        response_schemas={
            201: {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id"],
            },
            422: {"type": "object", "properties": {"error": {"type": "string"}}, "required": ["error"]},
        },
        exchange_ids=["a"],
    )


def make_probe(index: int, status: int = 422, code: str | None = "title_required") -> Exchange:
    return Exchange(
        id=f"p{index}",
        method="POST",
        url="http://t/api/tasks",
        path="/api/tasks",
        query={},
        status=status,
        request_json={},
        response_json={"error": code} if code else None,
        response_content_type="application/json",
    )


def make_bundle(**over) -> ObservationBundle:
    base = {
        "pages": [make_page()],
        "endpoints": [make_endpoint()],
        "probe_exchanges": [make_probe(1), make_probe(2, 404, "not_found")],
        "docs": ["Docs about the product."],
    }
    base.update(over)
    return ObservationBundle(**base)


def test_prompt_has_sections_and_content():
    prompt = make_bundle().to_prompt()
    headers = [line for line in prompt.splitlines() if line.startswith("# ")]
    assert headers == ["# Pages", "# Endpoints", "# Probes", "# Docs"]
    assert "http://t/p1" in prompt and "Page 1" in prompt
    assert "POST /api/tasks" in prompt
    assert "title" in prompt and "integer" in prompt and "date-time" in prompt
    assert "POST /api/tasks -> 422 title_required" in prompt
    assert "POST /api/tasks -> 404 not_found" in prompt
    assert "Docs about the product." in prompt
    assert "deadbeef" not in prompt  # screenshots are not part of the prompt


def test_probe_line_without_error_code_and_with_transport_error():
    unreachable = make_probe(3, 0, None).model_copy(update={"error": "unreachable"})
    bare = make_probe(4, 200, None)
    prompt = make_bundle(probe_exchanges=[unreachable, bare]).to_prompt()
    assert "POST /api/tasks -> 0 unreachable" in prompt
    assert "POST /api/tasks -> 200\n" in prompt or prompt.rstrip().endswith("POST /api/tasks -> 200")


def test_prompt_truncates():
    bundle = make_bundle(
        pages=[make_page(i, "t" * 2000) for i in range(30)],
        probe_exchanges=[make_probe(i) for i in range(200)],
        docs=["d" * 50_000],
    )
    for limit in (1000, 5_000, 60_000):
        assert len(bundle.to_prompt(limit)) <= limit
    assert len(bundle.to_prompt(10)) <= 10


def test_prompt_drops_docs_before_probes_before_page_detail():
    bundle = make_bundle(
        pages=[make_page(i, "t" * 300) for i in range(20)],
        probe_exchanges=[make_probe(i) for i in range(100)],
        docs=["DOCMARK" + "d" * 20_000],
    )
    full = bundle.to_prompt(10**9)
    assert "DOCMARK" in full and "title_required" in full and "Add task" in full

    no_docs_len = len(make_bundle(**{**bundle.__dict__, "docs": []}).to_prompt(10**9))
    trimmed = bundle.to_prompt(no_docs_len + 500)
    assert "DOCMARK" in trimmed and "title_required" in trimmed and len(trimmed) <= no_docs_len + 500

    no_docs = bundle.to_prompt(no_docs_len + 50)  # too little room for a useful docs excerpt
    assert "DOCMARK" not in no_docs and "title_required" in no_docs and "Add task" in no_docs

    no_probes_len = len(
        make_bundle(**{**bundle.__dict__, "docs": [], "probe_exchanges": []}).to_prompt(10**9)
    )
    no_probes = bundle.to_prompt(no_probes_len)
    assert "title_required" not in no_probes and "Add task" in no_probes

    tight = bundle.to_prompt(no_probes_len - 1)
    assert "Add task" not in tight  # page detail is dropped last
    assert "http://t/p1" in tight
    assert "# Endpoints" in tight and "POST /api/tasks" in tight


def test_empty_bundle():
    prompt = ObservationBundle(pages=[], endpoints=[], probe_exchanges=[], docs=[]).to_prompt()
    assert "# Pages" in prompt and "# Docs" in prompt
