# ReverseAI Foundation + Web Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Stage 0 (foundation) and a working Stage 1 skeleton of the ReverseAI clean-room pipeline for web targets, runnable end-to-end offline against a bundled demo app with a scripted fake LLM.

**Architecture:** A Python package `reverseai` with one module per pipeline concern: provenance ledger, zone-enforcing artifact store, provider-agnostic LLM gateway, sandboxes, intake, observation (HAR + Playwright + probing), oracle, spec builder, barrier, clean-zone implementation loop, parity, audit, pipeline orchestration and CLI. All LLM access goes through the gateway; all artifact access goes through the store, which enforces zone rules; every action is written to the hash-chained ledger. A bundled demo web app (`taskboard`) serves as the first internal benchmark target and as the fixture for integration tests.

**Tech Stack:** Python 3.12, uv, pydantic v2, httpx, typer, PyYAML, FastAPI + uvicorn (demo target and clone template), Playwright for Python (Chromium), pytest (+ respx not needed: use `httpx.MockTransport`).

**Spec:** `docs/spec/spec.md` (v0.1) and `docs/spec/decisions.md`. Read both before any task.

## Global Constraints

- Python `>=3.12`; dependency management with `uv`; package layout `src/reverseai/`; tests in `tests/` mirroring modules.
- Code, identifiers, comments, log messages: English. User-facing reports (evidence pack README, CLI summaries): Russian.
- Black-box only (D-005): no module may decompile or parse target JS for logic; JS/CSS/WASM/source maps from the target are stored only as `expression` artifacts in the `dirty` zone.
- Zone rule: the `clean` zone may read only `clean` and `released` artifacts. Enforced in `ArtifactStore.get`, never by convention.
- Every LLM call, artifact write/read, barrier release, approval and phase transition is appended to the project ledger.
- API keys are read from env vars named in config; they never appear in the ledger, artifacts, prompts or sandbox environments.
- Observation must not write to a target unless `ProjectCard.target_is_sandbox` is `True` (anti-goal: harming the target).
- Default rate limit toward any target: at most 2 requests/second (`delay_s=0.5`).
- Parity is measured on HTTP behavior and data, never on pixels or markup (anti-goal: visual copy).
- Acceptance thresholds default: overall parity `0.95`, critical scenarios `1.0` (spec §6.7, [ПРЕДП]).
- Code similarity threshold default: `0.05` containment (spec §6.8 placeholder until lawyer sets it).
- Clone template for Stage 1: `python-fastapi` (FastAPI + in-memory/SQLite). This deviates from spec §6.6 [ПРЕДП] TypeScript/Next.js for speed of the prototype; a TS template is a follow-up plan.
- Default models and prices come from `src/reverseai/config/default.yaml`; nothing model-specific is hardcoded elsewhere.
- pytest markers: `browser` (needs Playwright Chromium), `docker` (needs running Docker daemon), `live` (needs real API keys). Default `pytest` run excludes `live`; `browser`/`docker` tests skip automatically when unavailable.

## Review Focus

1. Agent file edits with `../`, absolute paths, or symlinks pointing outside the workspace — must be rejected without writing anything (Task 15).
2. Any text from the original (raw response bodies, JS, page text) leaking into the clean zone through parity feedback — feedback must pass the sanitizer and contain only short scalars (Task 16).
3. Ledger with a tampered middle line or a truncated last line after a crash — `verify()` reports `ok=False` with the first broken seq and does not raise (Task 2).
4. LLM output that is fenced JSON, has prose around JSON, or is invalid JSON — parsed when possible, one repair retry, then a clear `LLMOutputError` (Task 6 helper, used by Tasks 13 and 15).
5. Target that is unreachable, returns non-JSON, or returns huge bodies during observation/probing — exchange recorded with an error, bodies capped at 2 MB, run continues (Tasks 10, 11).

---

## File Structure

```
pyproject.toml                      # uv project, deps, pytest markers, console script `reverseai`
README.md                           # Russian overview + quickstart
CLAUDE.md                           # agent instructions: read spec/decisions first, zone rules, test commands
src/reverseai/
  __init__.py
  config/__init__.py                # Settings models + load_settings()
  config/default.yaml               # providers, models, prices, roles
  provenance/ledger.py              # hash-chained JSONL ledger
  zones/store.py                    # Zone enum, ArtifactStore, ZoneViolation
  llm/types.py                      # Message, LLMRequest, LLMResponse, Usage, ProviderError
  llm/policy.py                     # DataPolicy, PolicyViolation
  llm/providers.py                  # AnthropicProvider, OpenAICompatProvider, FakeProvider, build_providers()
  llm/gateway.py                    # Gateway: routing, policy, fallback, costs, ledger, transcripts
  llm/jsonout.py                    # extract_json(), complete_json()
  sandbox/base.py                   # RunResult, ServiceHandle, Sandbox protocol
  sandbox/local.py                  # LocalSandbox
  sandbox/docker.py                 # DockerSandbox
  project.py                        # ProjectCard, Attestation, Mode, Project, create_project(), risk_flags()
  observe/har.py                    # Exchange, classify(), parse_har()
  observe/contracts.py              # template_path(), infer_schema(), Endpoint, infer_endpoints()
  observe/explorer.py               # Playwright BFS explorer
  observe/probe.py                  # validation/404 probing on sandbox targets
  observe/bundle.py                 # ObservationBundle
  oracle/model.py                   # Scenario, ScenarioStep, Step, Expect
  oracle/normalize.py               # is_volatile(), normalize()
  oracle/standalone.py              # dependency-light runner (httpx only), copied into sandboxes
  oracle/build.py                   # build_scenarios()
  oracle/runner.py                  # run_scenarios() wrapper over standalone
  spec/model.py                     # BehaviorSpec and parts
  spec/builder.py                   # build_spec(), critique_spec()
  spec/render.py                    # render_markdown()
  barrier/sanitizer.py              # ExpressionIndex, sanitize_spec(), sanitize_text()
  barrier/release.py                # prepare_release(), Approval, release()
  implement/agent.py                # implement() loop
  implement/workspace.py            # safe_write(), snapshot()
  implement/templates/python-fastapi/{main.py,requirements.txt}
  parity/differential.py            # run_parity(), ParityReport, meets_threshold()
  parity/feedback.py                # feedback_for_clean_zone()
  audit/similarity.py               # code_similarity(), brand_mentions()
  audit/evidence.py                 # build_evidence_pack()
  pipeline.py                       # Phase, PipelineState, phase functions
  cli.py                            # typer app
  bench/server.py                   # serve_asgi() context manager
  bench/runner.py                   # run_benchmark()
bench/targets/taskboard/
  app.py                            # demo target ("TaskBoard Pro")
  static/app.js                     # demo target UI script (expression corpus)
  hidden_tests/test_behavior.py     # hidden behavior tests, BASE_URL env
tests/                              # mirrors src; tests/fixtures/ for scripted LLM outputs and fake clone
```

---

### Task 1: Project scaffold and settings

**Files:**
- Create: `pyproject.toml`, `src/reverseai/__init__.py`, `src/reverseai/config/__init__.py`, `src/reverseai/config/default.yaml`, `tests/conftest.py`
- Test: `tests/config/test_settings.py`

**Interfaces:**
- Produces:
  - `ProviderSpec(name: str, kind: Literal["anthropic","openai","fake"], base_url: str | None, api_key_env: str | None, jurisdiction: Literal["us","eu","cn","self"])`
  - `ModelSpec(id: str, provider: str, input_per_mtok: float, output_per_mtok: float, cached_input_per_mtok: float = 0.0)`
  - `RoleSpec(candidates: list[str], max_output_tokens: int = 8192)`
  - `Settings(providers: dict[str, ProviderSpec], models: dict[str, ModelSpec], roles: dict[str, RoleSpec])` with validator: every role candidate exists in `models`, every model's provider exists in `providers`.
  - `load_settings(path: Path | None = None) -> Settings` (default: packaged `default.yaml`).

Default YAML content (prices per 1M tokens, from report §LLM; model ids marked `# verify id` where unconfirmed):
- providers: `anthropic` (anthropic, `https://api.anthropic.com`, `ANTHROPIC_API_KEY`, us); `openai` (openai, `https://api.openai.com/v1`, `OPENAI_API_KEY`, us); `deepseek` (anthropic, `https://api.deepseek.com/anthropic`, `DEEPSEEK_API_KEY`, cn); `zai` (anthropic, `https://api.z.ai/api/anthropic`, `ZAI_API_KEY`, cn).
- models: `claude-opus-5-5` 4/20/0.20; `claude-sonnet-5-5` 2/10/0.10; `claude-haiku-5-5` 0.10/0.50/0.01; `gpt-6.1-sol` 2/10/0.10; `gpt-6-luna` 0.10/0.50/0.01; `deepseek-v4-pro` 1.32/3.96/0.044 (peak prices); `deepseek-v4.1-flash` 0.30/1.20/0.006; `glm-5.3` 1.40/4.40/0.26.
- roles: `planner`, `judge`, `spec_critic` → [claude-opus-5-5, gpt-6.1-sol]; `analyst`, `executor` → [claude-sonnet-5-5, gpt-6.1-sol, deepseek-v4-pro, glm-5.3]; `bulk` → [claude-haiku-5-5, gpt-6-luna, deepseek-v4.1-flash].

- [ ] **Step 1: Write pyproject** with deps `pydantic>=2.8`, `httpx>=0.27`, `typer>=0.12`, `pyyaml>=6`, `fastapi>=0.115`, `uvicorn>=0.30`, `playwright>=1.48`; dev deps `pytest>=8`, `ruff`. Console script `reverseai = "reverseai.cli:app"`. pytest config: `testpaths=["tests"]`, markers `browser`, `docker`, `live`, `addopts = "-m 'not live'"`. Package data includes `config/default.yaml` and `implement/templates/**`. Run `uv sync`.

- [ ] **Step 2: Write the failing tests**

```python
def test_default_settings_load():
    s = load_settings()
    assert s.roles["executor"].candidates[0] == "claude-sonnet-5-5"
    assert s.providers["deepseek"].jurisdiction == "cn"
    assert s.models["claude-opus-5-5"].output_per_mtok == 20

def test_unknown_candidate_rejected(tmp_path):
    # yaml where roles.executor.candidates = ["nope"]
    with pytest.raises(ValueError, match="nope"):
        load_settings(p)
```

- [ ] **Step 3: Run** `uv run pytest tests/config -v` — Expected: FAIL (ImportError).
- [ ] **Step 4: Implement** the models and `load_settings` in `src/reverseai/config/__init__.py`.
- [ ] **Step 5: Run** `uv run pytest tests/config -v` — Expected: PASS.
- [ ] **Step 6: Commit** `git commit -m "feat: project scaffold and settings"`

---

### Task 2: Provenance ledger

**Files:**
- Create: `src/reverseai/provenance/__init__.py`, `src/reverseai/provenance/ledger.py`
- Test: `tests/provenance/test_ledger.py`

**Interfaces:**
- Produces:
  - `LedgerEvent(seq: int, ts: str, type: str, zone: str, actor: str, payload: dict, prev_hash: str, hash: str)`
  - `LedgerVerification(ok: bool, count: int, broken_at: int | None, reason: str | None)`
  - `Ledger(path: Path)` with `append(type: str, zone: str, actor: str, payload: dict) -> LedgerEvent`, `events() -> list[LedgerEvent]`, `verify() -> LedgerVerification`.
- Hash: `sha256` hex of canonical JSON (`sort_keys=True, separators=(",",":"), ensure_ascii=False`) of all fields except `hash`. Genesis `prev_hash = "0"*64`. One JSON object per line; `append` is thread-safe (lock) and flushes + `os.fsync`. On open, `seq`/`prev_hash` continue from the last valid line.

- [ ] **Step 1: Write the failing tests**

```python
def test_chain_links(tmp_path):
    l = Ledger(tmp_path / "l.jsonl")
    a = l.append("x", "dirty", "test", {"k": 1}); b = l.append("y", "clean", "test", {})
    assert a.seq == 0 and b.seq == 1 and b.prev_hash == a.hash
    assert l.verify().ok and l.verify().count == 2

def test_reopen_continues_chain(tmp_path): ...  # new Ledger on same file -> next seq 2, prev_hash = last hash

def test_tampered_middle_line_detected(tmp_path):
    # append 3, rewrite line 1 payload -> verify().ok is False and broken_at == 1

def test_truncated_last_line_reported_not_raised(tmp_path):
    # append 2, append half a JSON line manually -> verify() == ok False, broken_at == 2, reason contains "parse"
```

- [ ] **Step 2: Run** `uv run pytest tests/provenance -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `Ledger`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat: hash-chained provenance ledger`

---

### Task 3: Zone-enforcing artifact store

**Files:**
- Create: `src/reverseai/zones/__init__.py`, `src/reverseai/zones/store.py`
- Test: `tests/zones/test_store.py`

**Interfaces:**
- Consumes: `Ledger.append`.
- Produces:
  - `class Zone(StrEnum): DIRTY="dirty"; RELEASED="released"; CLEAN="clean"; VERIFIER="verifier"`
  - `READ_RULES: dict[Zone, set[Zone]]` = DIRTY→{DIRTY, RELEASED}; RELEASED→{RELEASED}; CLEAN→{CLEAN, RELEASED}; VERIFIER→all.
  - `ArtifactRef(id: str, zone: Zone, kind: str, name: str, size: int, meta: dict)` — `id` = sha256 of content.
  - `class ZoneViolation(Exception)`
  - `ArtifactStore(root: Path, ledger: Ledger)` with `put(zone, kind, name, data: bytes, meta: dict | None = None) -> ArtifactRef`, `get(ref_id: str, reader: Zone) -> bytes`, `ref(ref_id) -> ArtifactRef`, `list(zone: Zone | None = None, kind: str | None = None) -> list[ArtifactRef]`, and helpers `put_json(zone, kind, name, obj) -> ArtifactRef`, `get_json(ref_id, reader) -> Any`.
- Storage: `root/<zone>/<id>` content, `root/index.jsonl` refs. Same content put twice in different zones → two index entries (ref lookup by `(id, zone)`; `get` picks the first entry readable by `reader`, else raises). Ledger events `artifact.put` and `artifact.read` (payload: id, kind, zone, reader); `ZoneViolation` also logs `zone.violation` before raising.

- [ ] **Step 1: Write the failing tests**

```python
def test_clean_cannot_read_dirty(store):
    r = store.put(Zone.DIRTY, "expression", "app.js", b"function a(){}")
    with pytest.raises(ZoneViolation): store.get(r.id, Zone.CLEAN)
    assert store.ledger.events()[-1].type == "zone.violation"

def test_clean_reads_released(store):
    r = store.put(Zone.RELEASED, "release_package", "pkg.json", b"{}")
    assert store.get(r.id, Zone.CLEAN) == b"{}"

def test_verifier_reads_all(store): ...
def test_list_filters_by_zone_and_kind(store): ...
def test_index_survives_reopen(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/zones -v` — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat: zone-enforcing artifact store`

---

### Task 4: LLM types, data policy, fake provider

**Files:**
- Create: `src/reverseai/llm/__init__.py`, `llm/types.py`, `llm/policy.py`, `llm/providers.py` (FakeProvider only in this task)
- Test: `tests/llm/test_types_policy_fake.py`

**Interfaces:**
- Produces:
  - `Message(role: Literal["user","assistant"], content: str)`
  - `LLMRequest(model: str, system: str | None, messages: list[Message], max_tokens: int, temperature: float | None = None)`
  - `Usage(input_tokens: int, output_tokens: int, cached_input_tokens: int = 0)`
  - `LLMResponse(text: str, model: str, provider: str, usage: Usage, cost_usd: float = 0.0)`
  - `class ProviderError(Exception)` with attrs `retryable: bool`, `status: int | None`.
  - `class Provider(Protocol): name: str; def complete(self, req: LLMRequest) -> LLMResponse`
  - `DataPolicy(allowed_jurisdictions: set[str] = {"us","eu","self"})`, `class PolicyViolation(Exception)`
  - `FakeProvider(name: str = "fake", script: list[str | Exception] | None = None, responder: Callable[[LLMRequest], str] | None = None)` — returns next scripted item (raising it if it is an Exception) or `responder(req)`; records `.requests: list[LLMRequest]`; usage = `len(text)//4` tokens each side.

- [ ] **Step 1: Write the failing tests**

```python
def test_fake_script_order_and_errors():
    p = FakeProvider(script=["a", ProviderError("busy", retryable=True, status=429), "b"])
    assert p.complete(req()).text == "a"
    with pytest.raises(ProviderError): p.complete(req())
    assert p.complete(req()).text == "b" and len(p.requests) == 3

def test_fake_responder(): ...
def test_default_policy_excludes_cn(): assert "cn" not in DataPolicy().allowed_jurisdictions
```

- [ ] **Step 2–4:** run (FAIL) → implement → run (PASS) with `uv run pytest tests/llm -v`.
- [ ] **Step 5: Commit** `feat: llm types, data policy, fake provider`

---

### Task 5: Real providers (Anthropic-compatible, OpenAI-compatible)

**Files:**
- Modify: `src/reverseai/llm/providers.py`
- Test: `tests/llm/test_providers_http.py`

Before coding, invoke the `claude-api` skill to confirm current Messages API request/response shape and headers.

**Interfaces:**
- Consumes: Task 4 types; `Settings`.
- Produces:
  - `AnthropicProvider(name: str, base_url: str, api_key: str, client: httpx.Client | None = None, timeout: float = 600)` — `POST {base_url}/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`; body `{model, max_tokens, system?, messages}`; text = concatenation of `content[].text` where `type=="text"`; usage from `input_tokens`, `output_tokens`, `cache_read_input_tokens`.
  - `OpenAICompatProvider(name, base_url, api_key, client=None, timeout=600)` — `POST {base_url}/chat/completions`, `Authorization: Bearer`; system prepended as `{"role":"system"}`; text = `choices[0].message.content`; usage `prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens`.
  - Both raise `ProviderError(retryable=status in {408, 409, 429, 500, 502, 503, 504, 529} or network error)`.
  - `build_providers(settings: Settings, env: Mapping[str, str] = os.environ) -> dict[str, Provider]` — skips providers whose key env var is missing; `fake` kind always built.

- [ ] **Step 1: Write the failing tests** (use `httpx.Client(transport=httpx.MockTransport(handler))`)

```python
def test_anthropic_parses_text_and_usage(): ...   # assert resp.text == "hi", usage.cached_input_tokens == 5, request header x-api-key == "k"
def test_anthropic_429_is_retryable(): ...         # ProviderError.retryable is True, status == 429
def test_anthropic_400_not_retryable(): ...
def test_openai_parses_and_sends_system_first(): ...  # sent messages[0]["role"] == "system"
def test_build_providers_skips_missing_keys():
    ps = build_providers(load_settings(), env={"ANTHROPIC_API_KEY": "x"})
    assert set(ps) == {"anthropic"}
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/llm -v`).
- [ ] **Step 5: Commit** `feat: anthropic- and openai-compatible providers`

---

### Task 6: Gateway with routing, policy, fallback, costs, transcripts + JSON output helper

**Files:**
- Create: `src/reverseai/llm/gateway.py`, `src/reverseai/llm/jsonout.py`
- Test: `tests/llm/test_gateway.py`, `tests/llm/test_jsonout.py`

**Interfaces:**
- Consumes: `Settings`, `Provider`, `Ledger`, `Zone`, `DataPolicy`.
- Produces:
  - `class GatewayError(Exception)`
  - `CostSummary(total_usd: float, by_role: dict[str, float], by_model: dict[str, float], calls: int)`
  - `Gateway(settings: Settings, providers: dict[str, Provider], ledger: Ledger, *, retries_per_candidate: int = 2, sleep: Callable[[float], None] = time.sleep, transcripts_dir: Path | None = None)`
  - `Gateway.complete(role: str, messages: list[Message], *, system: str | None = None, policy: DataPolicy, zone: Zone, actor: str) -> LLMResponse`
  - `Gateway.costs() -> CostSummary`
  - `cost_usd(model: ModelSpec, usage: Usage) -> float` = `(input-cached)*in + cached*cached_price + output*out` per 1e6.
  - `jsonout.extract_json(text: str) -> Any` — tries whole text, then first fenced ```json block, then the outermost `{...}`/`[...]` span; raises `LLMOutputError`.
  - `jsonout.complete_json(gateway, role, messages, *, model_cls: type[BaseModel] | None, system, policy, zone, actor) -> Any` — one repair retry: on parse/validation error, append the assistant text and a user message `"Your previous output was invalid: <error>. Reply with valid JSON only."`; second failure raises `LLMOutputError`.
- Routing: candidates of the role in order, filtered to models whose provider is built AND whose jurisdiction ∈ policy; none left → `PolicyViolation`. Per candidate: retry retryable errors up to `retries_per_candidate` with backoff `sleep(2**attempt)`; non-retryable or exhausted → next candidate; all fail → `GatewayError`.
- Ledger `llm.call` payload: role, model, provider, usage, cost_usd, prompt_sha256, response_sha256, attempt count. Never the API key. If `transcripts_dir` is set, write `{seq}.json` with full request/response (future training data, spec §7.3).

- [ ] **Step 1: Write the failing tests**

```python
def test_policy_filters_cn_models(): ...      # executor with only deepseek+zai providers built and default policy -> PolicyViolation
def test_fallback_after_retryable_exhaustion(): # sonnet fake raises 429 x3, gpt fake returns "ok" -> resp.model == "gpt-6.1-sol", sleep called twice
def test_cost_accounting():                     # usage 1_000_000 in / 0 out on sonnet -> cost_usd == 2.0; costs().by_role["executor"] == 2.0
def test_ledger_has_hash_not_prompt():          # event payload has prompt_sha256 and no "secret prompt" substring in ledger file
def test_extract_json_variants(): ...           # plain, fenced, prose-wrapped, invalid -> LLMOutputError
def test_complete_json_repairs_once(): ...      # script ["not json", '{"a":1}'] -> {"a":1}; ["x","y"] -> LLMOutputError
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/llm -v`).
- [ ] **Step 5: Commit** `feat: llm gateway with routing, policy, fallback and costs`

---

### Task 7: Sandboxes

**Files:**
- Create: `src/reverseai/sandbox/__init__.py`, `sandbox/base.py`, `sandbox/local.py`, `sandbox/docker.py`
- Test: `tests/sandbox/test_local.py`, `tests/sandbox/test_docker.py` (marker `docker`, skip if `docker info` fails)

**Interfaces:**
- Produces:
  - `RunResult(exit_code: int, stdout: str, stderr: str, timed_out: bool)` with `tail(n: int = 60) -> str` (last n lines of stdout+stderr).
  - `ServiceHandle(base_url: str, stop: Callable[[], None])`
  - `class Sandbox(Protocol): workdir: Path; isolated: bool; def run(self, cmd: list[str], *, timeout: float = 600) -> RunResult; def start(self, cmd: list[str], *, port: int, ready_path: str = "/", timeout: float = 30) -> ServiceHandle`
  - `LocalSandbox(workdir: Path, env_allowlist: tuple[str, ...] = ("PATH", "HOME", "LANG", "PYTHONPATH"))` — `isolated=False`; scrubbed env (only allowlisted vars); a leading `"python"` in `cmd` is replaced with `sys.executable` so the project venv is used; `start` polls `http://127.0.0.1:{port}{ready_path}` until any HTTP response.
  - `DockerSandbox(workdir: Path, image: str = "python:3.12-slim")` — `isolated=True`; `run` = `docker run --rm --network none -v {workdir}:/work -w /work {image} ...`; `start` publishes `-p 127.0.0.1:{port}:{port}` (bridge network, used only after implementation, spec §6.6).
  - `free_port() -> int`.

- [ ] **Step 1: Write the failing tests**

```python
def test_local_run_scrubs_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    r = LocalSandbox(tmp_path).run(["python", "-c", "import os;print(os.environ.get('ANTHROPIC_API_KEY'))"])
    assert r.stdout.strip() == "None"

def test_local_timeout(tmp_path): ...       # sleep 5 with timeout=0.5 -> timed_out True
def test_local_start_service(tmp_path): ... # python -m http.server on free_port -> GET base_url 200, stop() frees port
@pytest.mark.docker
def test_docker_has_no_network(tmp_path): ...  # python -c "urllib.request.urlopen('http://example.com')" -> exit_code != 0
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/sandbox -v`).
- [ ] **Step 5: Commit** `feat: local and docker sandboxes`

---

### Task 8: Project intake

**Files:**
- Create: `src/reverseai/project.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Consumes: `Ledger`, `ArtifactStore`, `DataPolicy`.
- Produces:
  - `class Mode(StrEnum): LEGACY="legacy"; IMPORT_SUBSTITUTION="import_substitution"`
  - `Attestation(lawful_access: bool, basis: str, signed_by: str, signed_at: str)`
  - `ProjectCard(name: str, mode: Mode, target_base_url: str, allowed_domains: list[str], target_is_sandbox: bool = False, attestation: Attestation, data_policy: DataPolicy = DataPolicy(), jurisdiction: str = "RU", brand_terms: list[str] = [], product_name: str, target_stack: str = "python-fastapi")`
  - `class IntakeError(Exception)`
  - `risk_flags(card: ProjectCard) -> list[str]` — IMPORT_SUBSTITUTION → `["patents", "trademarks", "tos_review"]`; `target_is_sandbox` False → append `"read_only_observation"`.
  - `Project(root: Path)` with attributes `card`, `ledger`, `store`, `dir`; `Project.load(path: Path) -> Project`.
  - `create_project(card: ProjectCard, projects_root: Path) -> Project` — raises `IntakeError` if `not attestation.lawful_access`, or if the host of `target_base_url` is not in `allowed_domains`, or if `product_name` case-insensitively contains any `brand_terms`. Creates `projects_root/<slug(name)>/` with `card.json`, `ledger.jsonl`, `artifacts/`, `state.json`; ledger event `project.created` with risk flags.

- [ ] **Step 1: Write the failing tests**

```python
def test_requires_attestation(tmp_path): ...            # lawful_access False -> IntakeError
def test_target_must_be_in_allowed_domains(tmp_path): ...
def test_product_name_cannot_reuse_brand(tmp_path): ... # brand "TaskBoard Pro", product_name "TaskBoard Lite" -> IntakeError
def test_import_substitution_flags(): assert risk_flags(card(mode=IMPORT_SUBSTITUTION)) [:3] == ["patents","trademarks","tos_review"]
def test_create_and_load_roundtrip(tmp_path): ...       # ledger first event type == "project.created"
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/test_project.py -v`).
- [ ] **Step 5: Commit** `feat: project intake with legal gate`

---

### Task 9: Demo target `taskboard` and ASGI test server

**Files:**
- Create: `bench/targets/taskboard/app.py`, `bench/targets/taskboard/static/app.js`, `bench/targets/taskboard/hidden_tests/test_behavior.py`, `src/reverseai/bench/__init__.py`, `src/reverseai/bench/server.py`
- Test: `tests/bench/test_taskboard.py`

**Behavior of the demo target (brand "TaskBoard Pro", in-memory state, `create_app()` factory):**
- `GET /` HTML page titled "TaskBoard Pro" with a form (`title` required text, `priority` select low|normal|high) and a list; loads `/static/app.js`, which renders tasks via `fetch('/api/tasks')` and submits the form via `POST /api/tasks`.
- `GET /api/tasks` → 200 list ordered by id. `GET /api/tasks/{id}` → 200 task or 404 `{"error":"not_found"}`.
- `POST /api/tasks {title, priority?}` → 201 `{id:int, title, priority, done:false, created_at: ISO8601}`; title trimmed; empty/missing/ >200 chars → 422 `{"error":"title_required"}` (or `"title_too_long"`); priority not in set → 422 `{"error":"invalid_priority"}`; default priority `normal`; an open task with the same title (case-insensitive) → 409 `{"error":"duplicate"}`.
- `PATCH /api/tasks/{id} {done: bool}` → 200 task; 404 as above.
- `DELETE /api/tasks/{id}` → 204; 404 as above.
- `GET /api/stats` → `{total, done, open}`.
- Hidden tests cover each rule above against `os.environ["BASE_URL"]` using httpx (≈15 tests). They are never stored in a project artifact store.
- `serve_asgi(app: ASGIApp, port: int | None = None) -> ContextManager[str]` — uvicorn in a thread, yields base URL, waits until ready, shuts down on exit.

- [ ] **Step 1: Write the failing tests** — `tests/bench/test_taskboard.py` starts `serve_asgi(create_app())` and runs the hidden test module with `BASE_URL` set via `pytest.main([...])` in a subprocess; assert exit code 0.
- [ ] **Step 2–4:** FAIL → implement app, JS, hidden tests, server → PASS (`uv run pytest tests/bench -v`).
- [ ] **Step 5: Commit** `feat: taskboard demo target and asgi test server`

---

### Task 10: HAR parsing, asset classification, API contract inference

**Files:**
- Create: `src/reverseai/observe/__init__.py`, `observe/har.py`, `observe/contracts.py`
- Test: `tests/observe/test_har.py`, `tests/observe/test_contracts.py`, fixture `tests/fixtures/taskboard.har` (recorded once from the demo target; may be generated in-test from Task 11 instead — keep a small hand-written HAR fixture here)

**Interfaces:**
- Produces:
  - `MAX_BODY_BYTES = 2_000_000`
  - `class AssetClass(StrEnum): API, DOCUMENT, EXPRESSION, MEDIA, OTHER` (values lowercase)
  - `classify(content_type: str, url: str) -> AssetClass` — js/css/wasm/`.map` → EXPRESSION; image/font/audio/video → MEDIA; html → DOCUMENT; json → API.
  - `Exchange(id: str, method: str, url: str, path: str, query: dict[str, str], status: int, request_json: Any | None, response_json: Any | None, response_content_type: str, error: str | None = None)` — `id` = short sha of method+url+index.
  - `ExpressionAsset(url: str, content: str)`
  - `HarParseResult(exchanges: list[Exchange], expression: list[ExpressionAsset], documents: list[ExpressionAsset], dropped_media: int, out_of_scope: int)`
  - `parse_har(har: dict, allowed_domains: list[str]) -> HarParseResult` — out-of-domain entries counted and dropped; bodies over `MAX_BODY_BYTES` → `error="body_too_large"`, body None; non-JSON body with JSON content type → `error="invalid_json"`.
  - `template_path(path: str) -> str` — segments that are all digits or UUIDs → `{id}`.
  - `infer_schema(examples: list[Any]) -> dict` — JSON-schema subset: `type` (union list if mixed), `properties`, `required` (keys present in all object examples), `items` (merged), `format: "date-time"` when all strings are ISO datetimes.
  - `Endpoint(method: str, path_template: str, statuses: list[int], request_schema: dict | None, response_schemas: dict[int, dict], exchange_ids: list[str])`
  - `infer_endpoints(exchanges: list[Exchange]) -> list[Endpoint]` — API-class exchanges only, grouped by (method, template), sorted.

- [ ] **Step 1: Write the failing tests**

```python
def test_classify(): assert classify("application/javascript", "/static/app.js") == AssetClass.EXPRESSION
def test_out_of_scope_dropped(): ...      # entry on cdn.example.org -> out_of_scope == 1
def test_large_body_capped(): ...         # error == "body_too_large"
def test_template_path(): assert template_path("/api/tasks/17") == "/api/tasks/{id}"
def test_infer_schema_required_and_datetime(): ...
def test_infer_endpoints_groups(): ...    # GET /api/tasks/1 and /api/tasks/2 -> one endpoint, statuses [200, 404]
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/observe -v`).
- [ ] **Step 5: Commit** `feat: har parsing and api contract inference`

---

### Task 11: Browser explorer and probing

**Files:**
- Create: `src/reverseai/observe/explorer.py`, `observe/probe.py`, `observe/bundle.py`
- Test: `tests/observe/test_explorer.py` (marker `browser`; skip if Chromium not installed), `tests/observe/test_probe.py`, `tests/observe/test_bundle.py`

Install browser once: `uv run playwright install chromium`.

**Interfaces:**
- Consumes: `ArtifactStore`, `Ledger`, `Zone`, `parse_har`, `infer_endpoints`, `ProjectCard`.
- Produces:
  - `FormField(name: str, type: str, required: bool, label: str | None)`, `FormInfo(action: str, method: str, fields: list[FormField])`
  - `PageObservation(url: str, title: str, links: list[str], forms: list[FormInfo], buttons: list[str], text_excerpt: str, screenshot_ref: str | None)` — `text_excerpt` ≤ 2000 chars.
  - `ExplorerConfig(start_url: str, allowed_domains: list[str], max_pages: int = 50, delay_s: float = 0.5, submit_forms: bool = False)`
  - `ExplorationResult(pages: list[PageObservation], har_ref: str, expression_refs: list[str])`
  - `explore(config: ExplorerConfig, card: ProjectCard, store: ArtifactStore) -> ExplorationResult` — raises `IntakeError` if `submit_forms and not card.target_is_sandbox`. BFS over in-domain links; HAR recorded with `record_har_path` + `record_har_content="embed"`; when `submit_forms`, fills each form with synthetic values by field type (text → `"Sample <n>"`, select → first option, checkbox → checked) and submits once per form. Stores: HAR (`har`), pages (`page`), screenshots (`screenshot`), expression assets (`expression`) — all `Zone.DIRTY`.
  - `probe_endpoints(base_url: str, endpoints: list[Endpoint], card: ProjectCard, *, client: httpx.Client | None = None, delay_s: float = 0.5) -> list[Exchange]` — raises `IntakeError` unless `card.target_is_sandbox`. For each POST/PATCH endpoint with a request schema: empty object body, each required field removed, each string field given a 201-char string, each field given wrong type; for each endpoint whose template contains `{id}`: request with id `999999`. Network errors → Exchange with `error="unreachable"`.
  - `ObservationBundle(pages: list[PageObservation], endpoints: list[Endpoint], probe_exchanges: list[Exchange], docs: list[str])` with `to_prompt(max_chars: int = 60_000) -> str` (pages summarized without screenshots; endpoints with schemas; probe results as `METHOD path -> status error_code`; docs truncated last).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.browser
def test_explore_taskboard_records_api_and_expression(project_on_taskboard): # submit_forms=True, target_is_sandbox=True
    res = explore(cfg, card, store)
    assert any(p.title == "TaskBoard Pro" for p in res.pages)
    har = parse_har(store.get_json(res.har_ref, Zone.VERIFIER), card.allowed_domains)
    assert any(e.method == "POST" and e.path == "/api/tasks" for e in har.exchanges)
    assert all(store.ref(r).zone == Zone.DIRTY for r in res.expression_refs)

def test_submit_forms_requires_sandbox(): ...  # IntakeError
def test_probe_finds_validation_errors(taskboard_url): ...  # some exchange status 422 with response_json["error"] == "title_required"; one 404
def test_probe_unreachable_recorded(): ...      # base_url on closed port -> error == "unreachable", no exception
def test_bundle_prompt_truncates(): ...         # len(to_prompt(1000)) <= 1000
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/observe -v`).
- [ ] **Step 5: Commit** `feat: playwright explorer, endpoint probing, observation bundle`

---

### Task 12: Oracle — scenarios, normalization, standalone runner

**Files:**
- Create: `src/reverseai/oracle/__init__.py`, `oracle/model.py`, `oracle/normalize.py`, `oracle/standalone.py`, `oracle/build.py`, `oracle/runner.py`
- Test: `tests/oracle/test_normalize.py`, `tests/oracle/test_build.py`, `tests/oracle/test_runner.py`

**Interfaces:**
- Consumes: `Exchange`, `Endpoint`, `template_path`, `serve_asgi` (tests).
- Produces:
  - `Step(method: str, path: str, json_body: Any | None = None, save: dict[str, str] = {})` — `path` may contain `{var}`; `save` maps var → JSON pointer into the response.
  - `Expect(status: int, json_shape: dict | None = None, json_equals: dict[str, Any] = {})` — keys are JSON pointers.
  - `ScenarioStep(step: Step, expect: Expect)`; `Scenario(id: str, title: str, steps: list[ScenarioStep], critical: bool = False, source_exchanges: list[str] = [])`
  - `normalize.is_volatile(value: Any) -> bool` (ISO datetime or UUID strings); `normalize.normalize(obj: Any) -> Any` (volatile → `"<volatile>"`).
  - `standalone.py` (imports only stdlib + httpx; operates on plain dicts): `run_scenario(base_url: str, scenario: dict, client) -> dict` returning `{"id", "passed", "failures": [{"step", "kind": "status"|"shape"|"value"|"error", "pointer", "expected", "actual"}]}`; `check_shape(schema: dict, value) -> list[str]` (pointers that violate); `main()` CLI: `python standalone.py scenarios.json --app "uvicorn main:app" --port N` restarts the app per scenario (reset by restart) and prints one JSON summary line `{"total", "passed", "failed": [first failure per scenario, max 30]}`.
  - `build.build_scenarios(exchanges: list[Exchange], endpoints: list[Endpoint]) -> list[Scenario]` — algorithm:
    1. Walk API exchanges in order; each becomes a step with `expect.status`, `json_shape` = endpoint response schema for that status.
    2. If an exchange's path contains a value equal to a scalar found at pointer P in an earlier response, replace it with `{v<k>}` and add `save={"v<k>": P}` to that earlier step; link the two exchanges.
    3. Connected components of links become multi-step scenarios; unlinked exchanges become single-step scenarios.
    4. `json_equals` = non-volatile scalar response fields whose value equals the request's value at the same key (echo), plus fields whose value is constant across all examples of that endpoint+status (e.g. `/error`, `/done`).
    5. Scenario is `critical` when it contains a 2xx write (POST/PATCH/PUT/DELETE).
    6. Deduplicate scenarios with identical (method, template, status, json_body keys) signatures.
  - `runner.run_scenarios(scenarios: list[Scenario], base_url: str, *, reset: Callable[[], None] | None = None, client: httpx.Client | None = None) -> list[ScenarioResult]` where `ScenarioResult(id: str, passed: bool, failures: list[StepFailure])`, `StepFailure(step: int, kind: str, pointer: str | None, expected: Any, actual: Any)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_normalize_timestamps_and_uuids(): ...
def test_check_shape_reports_missing_required(): ...
def test_build_links_create_then_get(): # POST returns {"id":5}, then GET /api/tasks/5 -> one scenario, step0.save == {"v0": "/id"}, step1.path == "/api/tasks/{v0}"
def test_build_marks_error_code_constant(): # two 422 examples with error "title_required" -> json_equals["/error"] == "title_required"
def test_runner_passes_on_taskboard(): # scenarios built from a scripted exchange list run green against serve_asgi(create_app()) with reset recreating the app
def test_runner_reports_status_failure(): ...
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/oracle -v`).
- [ ] **Step 5: Commit** `feat: behavior oracle with scenario builder and standalone runner`

---

### Task 13: Behavior spec model, LLM builder, critic, markdown

**Files:**
- Create: `src/reverseai/spec/__init__.py`, `spec/model.py`, `spec/builder.py`, `spec/render.py`, `tests/fixtures/llm/analyst_spec.json`, `tests/fixtures/llm/critic.json`
- Test: `tests/spec/test_builder.py`, `tests/spec/test_render.py`

**Interfaces:**
- Consumes: `Gateway`, `complete_json`, `ObservationBundle`, `Endpoint`, `DataPolicy`, `Zone`.
- Produces:
  - `Evidence(kind: Literal["page","exchange","endpoint","doc","expert"], ref: str)`
  - `SpecItem(id: str, title: str, description: str, confidence: Literal["high","medium","low"], evidence: list[Evidence])`
  - `Entity(name: str, fields: dict[str, str], description: str)`
  - `ApiContract(method: str, path: str, request_schema: dict | None, responses: dict[int, dict], description: str = "")`
  - `BehaviorSpec(version: int = 1, product_name: str, summary: str, features: list[SpecItem], entities: list[Entity], rules: list[SpecItem], api: list[ApiContract], gaps: list[str])` with `sha256() -> str` over canonical JSON.
  - `AnalystDraft(summary: str, features: list[SpecItem], entities: list[Entity], rules: list[SpecItem], gaps: list[str])` — the LLM-produced part.
  - `build_spec(gateway: Gateway, bundle: ObservationBundle, *, product_name: str, policy: DataPolicy) -> BehaviorSpec` — role `analyst`, zone DIRTY, actor `spec.analyst`; `api` is built deterministically from `bundle.endpoints` (no LLM); then `critique_spec`; if critic returns issues, one revision call to `analyst` with the issues; final issues appended to `gaps`.
  - `critique_spec(gateway, spec: BehaviorSpec, bundle, *, policy) -> list[str]` — role `spec_critic`, expects `{"issues": [str]}`.
  - System prompts state: describe behavior and rules in your own words; never copy code, UI wording, or brand names; use the product name given; mark unobserved areas as gaps; cite evidence refs from the bundle.
  - `render_markdown(spec: BehaviorSpec) -> str` — Russian section headings (`## Функции`, `## Сущности`, `## Правила`, `## API`, `## Пробелы`), each item with confidence and evidence refs.

- [ ] **Step 1: Write the failing tests** (FakeProvider with `responder` keyed by system prompt role marker)

```python
def test_build_spec_merges_llm_and_api(gateway_with_fixtures, bundle):
    spec = build_spec(gw, bundle, product_name="Tasklet", policy=DataPolicy())
    assert spec.product_name == "Tasklet"
    assert {(a.method, a.path) for a in spec.api} >= {("POST", "/api/tasks")}
    assert "critic issue A" in spec.gaps

def test_build_spec_invalid_json_twice_raises(): ...  # LLMOutputError
def test_render_has_sections(): assert "## Правила" in render_markdown(spec)
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/spec -v`).
- [ ] **Step 5: Commit** `feat: behavior spec builder with critic and markdown render`

---

### Task 14: Barrier — sanitizer, approval, release

**Files:**
- Create: `src/reverseai/barrier/__init__.py`, `barrier/sanitizer.py`, `barrier/release.py`
- Test: `tests/barrier/test_sanitizer.py`, `tests/barrier/test_release.py`

**Interfaces:**
- Consumes: `BehaviorSpec`, `Scenario`, `ArtifactStore`, `Zone`, `Project`.
- Produces:
  - `tokenize(text: str) -> list[str]` — `re.findall(r"\w+|[^\w\s]", text.lower())`.
  - `ExpressionIndex(shingle: int = 8)` with `add(text: str)`, `contains_span(tokens: list[str]) -> list[tuple[int, int]]` (matched token spans), built via `build_expression_index(texts: list[str], shingle: int = 8) -> ExpressionIndex`.
  - `Finding(kind: Literal["code","verbatim","brand","url"], location: str, excerpt: str)`; `SanitizeReport(findings: list[Finding])`.
  - `sanitize_text(text: str, *, location: str, index: ExpressionIndex, brand_terms: list[str], product_name: str, target_domains: list[str]) -> tuple[str, list[Finding]]` — code patterns (`function\s*\(`, `=>`, `\b(var|const|let)\s+\w+\s*=`, `\breturn\b.*;`, `\{\s*\}`) → `"[removed: code]"`; verbatim spans → `"[removed: verbatim]"`; brand terms (case-insensitive) → `product_name`; target domains/URLs → `"<original>"`.
  - `sanitize_spec(spec, index, *, brand_terms, target_domains) -> tuple[BehaviorSpec, SanitizeReport]` — applies to every prose field (summary, titles, descriptions, entity descriptions, api descriptions, gaps); leaves technical identifiers (field names, paths, schema keys) intact.
  - `release_scenarios(scenarios: list[Scenario], index) -> list[Scenario]` — keeps status and shape; keeps `json_equals` values only if scalar, ≤ 64 chars when stringified, and no finding from `sanitize_text`; clears `source_exchanges`.
  - `PreparedRelease(spec: BehaviorSpec, scenarios: list[Scenario], report: SanitizeReport, spec_sha256: str)`
  - `prepare_release(project: Project, spec: BehaviorSpec, scenarios: list[Scenario]) -> ArtifactRef` — builds index from all DIRTY `expression` and `page` artifacts, sanitizes, stores `PreparedRelease` (DIRTY, kind `release_draft`) and the rendered markdown (DIRTY, kind `release_draft_md`) for human review.
  - `Approval(approver: str, role: Literal["operator","customer_analyst"]  # D-010 (was customer_lawyer), approved_at: str, spec_sha256: str)`
  - `class ReleaseError(Exception)`
  - `release(project: Project, draft_ref: str, approval: Approval) -> ArtifactRef` — raises `ReleaseError` if `approval.spec_sha256 != draft.spec_sha256` or a re-run of the sanitizer on the draft spec yields findings; writes `{spec, scenarios, approval}` as RELEASED kind `release_package`; ledger `barrier.approved` and `barrier.release` with hashes.

- [ ] **Step 1: Write the failing tests**

```python
def test_removes_verbatim_js(): # index from taskboard app.js; description containing an 8-token slice of it -> "[removed: verbatim]", finding kind "verbatim"
def test_removes_code_pattern(): ...
def test_replaces_brand_and_domain(): ...  # "TaskBoard Pro at app.example.com" -> "Tasklet at <original>"
def test_api_paths_untouched(): ...
def test_release_scenarios_drop_long_values(): ...
def test_release_rejects_hash_mismatch(project): ...      # ReleaseError
def test_release_writes_released_zone_and_ledger(project): # ref.zone == Zone.RELEASED; ledger types include "barrier.release"; clean zone can read it
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/barrier -v`).
- [ ] **Step 5: Commit** `feat: barrier sanitizer and approved release`

---

### Task 15: Clean-zone implementation loop

**Files:**
- Create: `src/reverseai/implement/__init__.py`, `implement/workspace.py`, `implement/agent.py`, `implement/templates/python-fastapi/main.py`, `implement/templates/python-fastapi/requirements.txt`, `tests/fixtures/fake_clone/main.py` (hand-written clone of taskboard API behavior written only from the spec fixture, used by the scripted executor)
- Test: `tests/implement/test_workspace.py`, `tests/implement/test_agent.py`

**Interfaces:**
- Consumes: `ArtifactStore.get_json(ref, Zone.CLEAN)`, `Gateway`, `complete_json`, `Sandbox`, `render_markdown`, `oracle/standalone.py`.
- Produces:
  - `workspace.safe_write(root: Path, rel_path: str, content: str) -> Path` — raises `WorkspaceError` for absolute paths, `..` escapes, or a resolved path outside `root` (including via symlink); max file size 500 KB.
  - `workspace.snapshot(root: Path, max_file_chars: int = 20_000) -> str` — file tree plus contents of text files (skips the copied oracle runner and `oracle_scenarios.json`).
  - `FileEdit(path: str, content: str)`; `AgentTurn(notes: str = "", edits: list[FileEdit] = [], done: bool = False)`
  - `ImplementConfig(max_iterations: int = 20, stack: str = "python-fastapi", app_cmd: str = "uvicorn main:app", feedback: list[str] = [])`
  - `ImplementResult(iterations: int, passed: bool, total: int, passed_count: int, workspace: Path)`
  - `implement(project: Project, release_ref: str, gateway: Gateway, sandbox: Sandbox, config: ImplementConfig) -> ImplementResult`:
    1. Load package via `store.get_json(release_ref, Zone.CLEAN)`; copy template into `sandbox.workdir`; write `oracle_scenarios.json` (released scenarios) and copy `oracle/standalone.py` as `oracle_runner.py`.
    2. Planner call (role `planner`, zone CLEAN, actor `clean.planner`): returns plain-text plan, kept in the prompt.
    3. Loop ≤ `max_iterations`: executor call (role `executor`, zone CLEAN) with spec markdown + plan + `config.feedback` + `snapshot()` + last test summary; parse `AgentTurn`; apply edits via `safe_write` (a rejected edit is reported back to the model next turn, not fatal); run `python oracle_runner.py oracle_scenarios.json --app "<app_cmd>" --port <free>` in the sandbox; parse the summary line.
    4. Finish only when all scenarios pass; if the model sets `done` while tests fail, next prompt starts with `"Tests are still failing; you are not done."`.
    5. Ledger `implement.iteration` per loop with passed/total; result written as CLEAN artifact kind `code` (zip of workspace) at the end.
  - Prompts contain no target URL and the gateway never receives anything read from DIRTY artifacts (guaranteed by step 1 being the only read).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("bad", ["../x.py", "/etc/passwd", "a/../../x"])
def test_safe_write_rejects_escape(tmp_path, bad): ...
def test_safe_write_rejects_symlink_escape(tmp_path): ...
def test_implement_reaches_green_with_scripted_executor(released_project, tmp_path):
    # executor script: turn1 = broken main.py, turn2 = fixtures/fake_clone/main.py
    res = implement(p, ref, gw, LocalSandbox(tmp_path / "ws"), ImplementConfig(max_iterations=3))
    assert res.passed and res.iterations == 2
def test_implement_cannot_take_dirty_ref(project): ...  # ZoneViolation for a DIRTY ref
def test_done_flag_ignored_when_failing(): ...          # second executor prompt starts with "Tests are still failing"
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/implement -v`).
- [ ] **Step 5: Commit** `feat: clean-zone implementation loop with oracle gate`

---

### Task 16: Parity check and sanitized feedback

**Files:**
- Create: `src/reverseai/parity/__init__.py`, `parity/differential.py`, `parity/feedback.py`
- Test: `tests/parity/test_differential.py`, `tests/parity/test_feedback.py`

**Interfaces:**
- Consumes: `run_scenarios`, `Scenario` (full, from DIRTY), `ExpressionIndex`, `sanitize_text`.
- Produces:
  - `ScenarioParity(id: str, title: str, critical: bool, original_ok: bool, clone_ok: bool, failures: list[StepFailure])`
  - `ParityReport(total: int, passed: int, critical_total: int, critical_passed: int, unstable: list[str], results: list[ScenarioParity])` with properties `ratio` and `critical_ratio` (1.0 when denominator 0).
  - `run_parity(scenarios: list[Scenario], original_url: str, clone_url: str, *, reset_original=None, reset_clone=None) -> ParityReport` — scenarios failing on the original are `unstable` and excluded from totals.
  - `meets_threshold(report: ParityReport, overall: float = 0.95, critical: float = 1.0) -> bool`
  - `feedback_for_clean_zone(report: ParityReport, scenarios: list[Scenario], index: ExpressionIndex, *, brand_terms, product_name, target_domains) -> list[str]` — one line per failing scenario: `"<sanitized title>: step <n> <METHOD> <path template>: expected <kind> <pointer> = <value or type>"`; values included only if scalar, ≤ 64 chars, and sanitizer-clean; otherwise `"(value withheld)"`; max 30 lines. Ledger event `parity.feedback` with sha of the list.

- [ ] **Step 1: Write the failing tests**

```python
def test_parity_full_on_identical_apps(): ...       # taskboard vs taskboard -> ratio 1.0
def test_parity_detects_missing_rule(): ...         # clone app without duplicate check -> a 409 scenario fails, critical_ratio < 1
def test_unstable_excluded(): ...
def test_feedback_withholds_long_and_verbatim(): ... # 200-char expected value -> "(value withheld)"; no line contains an 8-token span of app.js
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/parity -v`).
- [ ] **Step 5: Commit** `feat: differential parity check and sanitized feedback`

---

### Task 17: Audit — similarity and evidence pack

**Files:**
- Create: `src/reverseai/audit/__init__.py`, `audit/similarity.py`, `audit/evidence.py`
- Test: `tests/audit/test_similarity.py`, `tests/audit/test_evidence.py`

**Interfaces:**
- Consumes: `tokenize`, `Ledger.verify`, `ArtifactStore`, `ParityReport`, `SanitizeReport`.
- Produces:
  - `SimilarityReport(threshold: float, max_score: float, per_file: dict[str, float], ok: bool)`
  - `code_similarity(code_files: dict[str, str], expression_texts: list[str], *, shingle: int = 8, threshold: float = 0.05) -> SimilarityReport` — score per file = fraction of the file's token shingles present in the corpus shingles.
  - `brand_mentions(code_files: dict[str, str], brand_terms: list[str]) -> list[str]` — `"path:line"` entries.
  - `build_evidence_pack(project: Project, *, parity: ParityReport, similarity: SimilarityReport, brand_hits: list[str], out_dir: Path) -> Path` — writes a directory and a `.zip` with: `ledger.jsonl`, `ledger_verification.json`, `release/` (all `release_package` artifacts incl. approvals), `sanitize_report.json`, `parity_report.json`, `similarity_report.json`, `models_used.json` (aggregated model/provider/calls/cost from `llm.call` events), `zones_access.json` (all `artifact.read` events grouped by reader zone), and `README.md` in Russian summarizing: ledger integrity, approvals, parity ratio, critical ratio, max similarity vs threshold, brand hits, risk flags from intake. Returns zip path; ledger `audit.evidence_pack`.

- [ ] **Step 1: Write the failing tests**

```python
def test_identical_code_scores_one(): ...
def test_independent_code_scores_low(): # fixtures/fake_clone/main.py vs taskboard app.js -> max_score < 0.05
def test_brand_mentions(): ...
def test_evidence_pack_contents(project_after_release): # zip contains README.md, ledger_verification.json with "ok": true; README contains "Целостность журнала"
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/audit -v`).
- [ ] **Step 5: Commit** `feat: similarity audit and evidence pack`

---

### Task 18: Pipeline orchestration and CLI

**Files:**
- Create: `src/reverseai/pipeline.py`, `src/reverseai/cli.py`
- Test: `tests/test_pipeline.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `class Phase(StrEnum): INTAKE, OBSERVE, ORACLE, SPEC, PREPARE_RELEASE, RELEASE, IMPLEMENT, PARITY, AUDIT` (values lowercase).
  - `PipelineState(completed: list[Phase], refs: dict[str, str], parity_rounds: int = 0)` persisted in `state.json`; `load_state(project) -> PipelineState`, `save_state(project, state)`.
  - Phase functions (each checks prerequisites via state, records `phase.completed` in ledger, saves refs):
    - `run_observe(project, *, max_pages=50, submit_forms=False, probe=False) -> None`
    - `run_oracle(project) -> None`
    - `run_spec(project, gateway) -> None`
    - `run_prepare_release(project) -> None`
    - `run_release(project, approval: Approval) -> None`
    - `run_implement(project, gateway, sandbox, *, feedback: list[str] = []) -> ImplementResult`
    - `run_parity_phase(project, clone_url: str, *, reset_original=None, reset_clone=None) -> ParityReport` (stores report as VERIFIER artifact)
    - `run_build_loop(project, gateway, sandbox_factory: Callable[[], Sandbox], *, max_rounds: int = 3, reset_original=None) -> ParityReport` — implement → start clone via `sandbox.start` → parity → if not `meets_threshold`, `feedback_for_clean_zone` → implement again.
    - `run_audit(project, out_dir: Path) -> Path`
  - `build_gateway(project, settings: Settings | None = None, env=os.environ) -> Gateway` — transcripts in `project.dir / "transcripts"`.
  - CLI (`typer`), all commands take `--project PATH`: `init` (from a YAML card file), `observe`, `oracle`, `spec`, `prepare-release` (prints markdown path and spec sha256), `approve --approver NAME --role ROLE --sha SHA`, `build` (loop), `audit --out DIR`, `ledger-verify`, `costs`, `status`. CLI messages in Russian.

- [ ] **Step 1: Write the failing tests**

```python
def test_phase_order_enforced(project): # run_spec before run_oracle -> RuntimeError mentioning "oracle"
def test_cli_status_and_ledger_verify(tmp_path): # CliRunner: init then status -> exit 0, output contains "intake"; ledger-verify -> "ok"
```

- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/test_pipeline.py tests/test_cli.py -v`).
- [ ] **Step 5: Commit** `feat: pipeline orchestration and cli`

---

### Task 19: Benchmark harness and offline end-to-end test

**Files:**
- Create: `src/reverseai/bench/runner.py`, `tests/e2e/test_taskboard_pipeline.py`, `tests/fixtures/llm/planner.txt`
- Modify: `src/reverseai/cli.py` (add `bench --target taskboard [--live]`)

**Interfaces:**
- Consumes: all phases, `serve_asgi`, `create_app`, hidden tests.
- Produces:
  - `BenchResult(target: str, parity_ratio: float, critical_ratio: float, hidden_passed: int, hidden_total: int, cost_usd: float, duration_s: float, similarity_max: float)`
  - `run_benchmark(target: str, *, gateway: Gateway, workdir: Path, sandbox_factory) -> BenchResult` — creates a project with `target_is_sandbox=True`, runs observe (with `submit_forms=True`, `probe=True`), oracle, spec, prepare-release, auto-approval as `operator` (bench only, ledger notes `auto_approved: true`), build loop, audit; then runs hidden tests (pytest subprocess, `BASE_URL` = clone) and counts results. Writes `bench_result.json`.
  - E2E test (marker `browser`): FakeProvider responder routing by role → analyst/critic fixtures, planner text, executor returns `fixtures/fake_clone/main.py`; asserts `parity_ratio >= 0.95`, `critical_ratio == 1.0`, `hidden_passed == hidden_total`, `similarity_max < 0.05`, ledger verifies, evidence zip exists, and no CLEAN-zone `artifact.read` of a DIRTY artifact in the ledger.
  - `--live` uses real providers from env and the default policy; marker `live`.

- [ ] **Step 1: Write the failing e2e test** as above.
- [ ] **Step 2: Run** `uv run pytest tests/e2e -v` — FAIL.
- [ ] **Step 3: Implement** `run_benchmark` and the CLI command; adjust `fake_clone` until the hidden tests pass (the fake clone is written from `analyst_spec.json`, never from `app.py`).
- [ ] **Step 4: Run** `uv run pytest -v` (whole suite) — Expected: PASS (browser/docker tests skipped only if unavailable).
- [ ] **Step 5: Commit** `feat: benchmark harness and offline e2e pipeline test`

---

### Task 20: Developer docs

**Files:**
- Create: `README.md`, `CLAUDE.md`
- Modify: `docs/spec/decisions.md` (add D-006: Stage 1 clone template is python-fastapi, marked as engineering call pending founder confirmation)

- [ ] **Step 1:** README (Russian): what the platform does, pipeline diagram, quickstart (`uv sync`, `uv run playwright install chromium`, `uv run pytest`, `uv run reverseai bench --target taskboard`), env vars for providers, zone rules, where spec/decisions live.
- [ ] **Step 2:** CLAUDE.md: read `docs/spec/decisions.md` and `docs/spec/spec.md` first; never let clean-zone code read dirty artifacts; all LLM calls via `Gateway`; test commands and markers; record new decisions in `decisions.md`.
- [ ] **Step 3: Run** `uv run pytest` — PASS; `uv run ruff check src tests` — no errors.
- [ ] **Step 4: Commit** `docs: readme, claude.md, decision D-006`

---

## Not in this plan (follow-up plans)

- Web console (spec §9.1), Temporal-based durable orchestration, multi-tenant security (§9.3).
- TypeScript/Next.js clone template; desktop observation (Stage 4); own weights/on-prem (Stage 5).
- mitmproxy capture for non-browser clients; login flows for targets requiring auth.
- Expert Q&A channel (agents asking the customer's analyst, spec §6.2) and document ingestion command.
- License scanning of clone dependencies; patent/trademark checklists beyond intake flags.
