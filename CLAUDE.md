# ReverseAI — notes for coding agents

Clean-room reimplementation platform: black-box observation of a web target, a human-approved behavioral spec, and a clone written by agents that never see the original.

## Read first

1. `docs/spec/decisions.md` — decision log (source of truth; D-001..D-016).
2. `docs/spec/spec.md` — product spec; items marked **[ПРЕДП]** are unconfirmed assumptions.
3. `docs/superpowers/plans/2026-10-20-foundation-and-web-pipeline.md` — implementation plan of the prototype.

## Architecture (`src/reverseai/`)

- `config` — settings loader; `default.yaml` holds providers, models, prices, role routing.
- `provenance` — append-only hash-chained ledger (`ledger.jsonl`) with `verify()`; appends lock `ledger.jsonl.lock` so several processes share one chain.
- `zones` — `Zone` enum and `ArtifactStore`; read rules enforced in `get`.
- `llm` — `Gateway` (role routing, data policy, retry/fallback, cost), providers, JSON-output helper.
- `sandbox` — `LocalSandbox` (not isolated) and `DockerSandbox` (isolated, no network for `run`).
- `project` — project card, intake/legal gate, project directory layout, `project_lock` (`pipeline.lock`, D-015: every mutating CLI command, console job and approval holds it; a second one is refused at once).
- `observe` — Playwright explorer, HAR parsing, API probe, observation bundle, endpoint contracts.
- `oracle` — executable behavior scenarios; `standalone.py` is the dependency-light runner copied into sandboxes.
- `spec` — behavioral spec model, builder (analyst + critic), renderer.
- `barrier` — sanitizer and release gate (human approval bound to the package SHA-256 of spec + scenarios).
- `implement` — clone agent, workspace file rules, `templates/` (python-fastapi).
- `parity` — differential run: full scenarios on the original, released projections on the clone; sanitized feedback to the clean zone.
- `audit` — code similarity check and evidence pack.
- `pipeline` — phase state machine and orchestration of all steps; re-running a phase invalidates every later one.
- `cli` — `reverseai` Typer app (global `--lang en|ru`); `messages` — phase labels, error messages and build summary lines shared with the console.
- `i18n` — `t()`, `Labels`, the active language (context variable) and the `en` / `ru` catalogs.
- `console` — web console (`reverseai console`): FastAPI + Jinja pages over the same pipeline calls, background job runner, `read/` view models, `routes/`, `templates/`, `static/`.
- `bench` — benchmark harness and bundled in-process target server.

## Hard rules

- Zones: clean-zone code reads artifacts only via `ArtifactStore.get(..., Zone.CLEAN)`, and only released/clean ones. Never read dirty artifacts, raw HAR, response bodies or page text from clean-zone code, prompts or parity feedback. Do not bypass `ArtifactStore`.
- Black box only (D-005): never decompile or parse target JS for logic; target JS/CSS/WASM/source maps are stored only as `expression` artifacts in the dirty zone.
- All LLM calls go through `Gateway` with a role (`planner`, `judge`, `spec_critic`, `analyst`, `executor`, `bulk`). Never call a provider SDK or HTTP API directly. Model ids and prices live only in `default.yaml`.
- Never put API keys into the ledger, artifacts, prompts or sandbox environments; keys come from env vars named in config.
- Write to a target (form submits, probing, parity replays of write scenarios) only when `ProjectCard.target_is_sandbox` is true. Keep the default rate limit toward targets (at most 2 req/s; observation and parity apply it).
- Prose crossing the barrier goes through `sanitize_text` (code, verbatim, brand, domains); identifiers (spec ids, entity and field names, API and step paths, request-body keys and strings) go through `mask_identifier` (brand and domains only, URL-safe in paths, a target origin opening a path is dropped; see D-008, D-012). Brand matching is one rule everywhere (barrier, audit): case-insensitive, also glued inside identifiers (`acme_id`, `AcmeTasks`, `task-board`). JSON keys are renamed by one package-wide `KeyRenames` map in bodies, request/response schemas, entity fields, `json_equals` pointers and `save` maps; methods and schema types are kept. Request-body string values that match the original's expression only raise a non-blocking `body_warning`. Expected values cross only under `releasable_value`; parity feedback shows paths and pointers by `mask_identifier` (one rule for release and feedback).
- `oracle/standalone.py` must stay stdlib + `httpx` only and must never import `reverseai`.
- Agent file edits must stay inside the workspace (reject `../`, absolute paths, symlinks escaping it).
- Every LLM call, artifact read/write, release, approval and phase transition goes to the ledger.
- Parity is measured on HTTP behavior and data, never on pixels or markup.

## Language

User-facing text (CLI output, console, job logs, errors, release draft, spec markdown, evidence pack) goes through the i18n catalogs (`src/reverseai/i18n/`: `en.py` default, `ru.py` supported, `t(key, **params)`, plural forms via `count=`) and is never hardcoded; add every new string to both catalogs (tests check keys, placeholders and that no Cyrillic lives outside `ru.py`). The CLI takes `--lang` / `REVERSEAI_LANG`; the console takes `--lang` and a per-browser EN/RU cookie; jobs inherit the request's language. LLM prompts stay English. `README.md` is English; `README.ru.md` is its Russian counterpart — keep both in sync. Code, identifiers, comments and log messages are English.

## Commands

Always use `uv` (system python is not the project's).

```bash
uv sync
uv run playwright install chromium
uv run pytest                        # default run excludes `live`
uv run pytest -m browser tests/e2e   # full offline e2e (needs Chromium)
uv run pytest -m docker              # needs a running Docker daemon
uv run pytest -m live                # needs real API keys
uv run ruff check src tests
uv run reverseai --help
```

Markers: `browser` (Playwright Chromium), `docker` (Docker daemon), `live` (real API keys). `browser`/`docker` tests skip when unavailable.

## Decisions

Any new product or engineering decision (stack, thresholds, provider policy, scope) must be recorded in `docs/spec/decisions.md` (next free `D-NNN`, date, source). Mark engineering calls that need the founder's sign-off as pending.
