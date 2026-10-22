# ReverseAI web console — design

Status: approved for overnight build by the founder (2026-10-22: "доделай интерфейс полностью … без подтверждений, завтра я всё проверю"). Visual direction approved as a starting point from the mockup canvas https://claude.ai/artifact/X5q9h2whsU4Uud4jNwYpqr ("я оценю, если что переделаешь").

## Intent

Operators run the clean-room pipeline today only through the `reverseai` CLI. The console gives the operator one place to create a project, run each phase, review and approve the release package, watch parity and download the evidence pack — in a minimal SpaceX/X-style UI with dark and light themes. Everything the console shows or does must go through the existing pipeline modules so the clean-room guarantees (zones, ledger, barrier) stay exactly as they are.

## Users

- **Operator of the platform** (primary): creates projects, runs phases, approves the package at the barrier.
- **Customer analyst** (secondary): may approve the package instead of the operator (role `customer_analyst`).
- **Customer lawyer**: does NOT act in the pipeline. They receive the finished evidence pack at the end (founder decision D-010). The console only offers its download.

## Goals

1. Projects list: every project under `--projects-root`, its mode, target host, completed phases (9-step progress), last activity.
2. New project form → `create_project` (ProjectCard incl. attestation, allowed domains, sandbox flag, brand terms, product name, data policy jurisdictions). Intake errors shown in Russian next to the form.
3. Project overview: mission-style timeline of the 9 phases with time and one-line detail per phase; KPIs (parity, critical parity, code similarity vs threshold, LLM cost); zones with artifact counts; ledger events table (latest first, filter by type prefix, hashes shown short); ledger integrity status.
4. Run phases from the UI: observe (max pages, submit forms, probe), oracle, spec, prepare-release, build (max rounds, allow-unstable), audit. One background job per project at a time; job status, start/end time and a terse log tail visible on the page (auto-refresh by polling); errors (PhaseOrderError, IntakeError, ReleaseError, environment errors, missing API keys) shown as Russian messages, never tracebacks.
5. Release review: tabs Specification (rendered sections), Scenarios (method, path, body, expectations, critical flag), Cleanup (sanitizer findings, withheld values, oracle-dropped scenarios). Package SHA-256 shown. Approve form: approver name, role (operator / customer analyst), confirmation checkbox, button → `run_release` with `Approval(package_sha256=<draft hash>)`. After release: approved state with time and approver.
6. Parity & evidence: KPIs (ratio, critical ratio, unstable, rounds), per-scenario table (original/clone pass, withheld mismatches), similarity meter with threshold, brand mentions, evidence pack file list, download of the zip, sandbox-isolation warning, "not legal advice" note.
7. Costs page or section: totals by role and model from the ledger (same numbers as `reverseai costs`).
8. Dark and light themes; toggle in the header; choice remembered in `localStorage` (wrapped in try/catch); default follows `prefers-color-scheme`.
9. Works at phone width (header wraps, tables scroll inside their box, timeline scrolls horizontally).

## Non-goals (this version)

Multi-user accounts and permissions; editing the spec in the browser; live websockets; a customer portal; running more than one job per project; hosting on the public internet.

## Anti-goals

- The console must never let clean-zone content be mixed with dirty content or bypass `ArtifactStore`/`Gateway`/barrier rules.
- Never render target-originated content unescaped (it is untrusted: page text, HAR bodies, spec prose).
- Never show API keys or put them in pages, logs or job output.
- No visual noise: no gradients, no shadows, no emoji, no accent colors beyond status (orange for warnings).

## How it is built (decided)

- **Stack:** FastAPI + Jinja2 server-rendered pages inside the `reverseai` package (`src/reverseai/console/`), one static CSS file with design tokens, one small vanilla JS file (theme toggle, tab switching, job polling, confirm checkbox). No Node/bundler. Rationale: same language and process as the pipeline, no build step, testable with FastAPI TestClient + Playwright.
- **Entry point:** `reverseai console --projects-root DIR [--host 127.0.0.1] [--port 8765]`. Binds to loopback by default. A non-loopback host requires `REVERSEAI_CONSOLE_TOKEN` (checked as a cookie set via `/login?token=` or `Authorization: Bearer`); otherwise refuse to start with a Russian error.
- **Visual system (from the mockup):**
  - Dark: background `#000000`, text `#f0f0fa`, muted `#9a9aa6`, hairlines `rgba(240,240,250,0.14)`, ghost fill `rgba(240,240,250,0.06)`, warning `#ffa94d`.
  - Light: background `#fafafa`, text `#0a0a0c`, muted `#5c5c66`, hairlines `rgba(10,10,12,0.14)`, ghost fill `rgba(10,10,12,0.04)`, warning `#a85400`.
  - Type: Barlow (uppercase, tracked 0.14–0.32em) for wordmark, nav, labels and big numbers; Inter for text; JetBrains Mono for hashes, times, paths. Google Fonts link with system fallbacks (`system-ui`, `ui-monospace`).
  - Shapes: hairline separators instead of cards; pill buttons (primary = inverted text/background, secondary = ghost with hairline); 4px radius for panels/inputs; no shadows.
  - Layout: max width 1360px, 40px side padding (16px on phones), header 72px with wordmark `REVERSEAI`, nav, theme toggle, operator initials.
  - The mockup source (`Main.dc.html`, `Release.dc.html`, `Parity.dc.html`) is the reference for spacing, hierarchy and copy.
- **Reading project data:** through existing APIs only (`Project`, `load_state`, ledger `events()`/`verify()`, `ArtifactStore.get(..., Zone.VERIFIER)`). Artifact ids are content hashes, so the console caches decoded artifacts per process by id — each artifact read is logged once per server run, not on every page view.
- **Jobs:** an in-process job runner (thread per job, one active job per project, registry in memory); each job calls the same pipeline function the CLI calls, captures a terse log (no secrets), records start/end and outcome. The CLI and the console must produce identical ledger effects for the same action.
- **Security headers:** Content-Security-Policy allowing self + Google Fonts only; no inline scripts; Jinja autoescape on; POST actions protected by a per-process CSRF token in forms.
- **Language:** all UI copy in Russian; code and identifiers in English (CLAUDE.md).

## Left to the builder

Template/partial structure, exact URL scheme, polling interval, how log tails are captured, empty states' wording, small layout details within the visual system.

## Done when

- All goals above work against a real project produced by the pipeline (fixture built like `tests/test_pipeline.py`), covered by TestClient tests per page and action, plus a Playwright smoke test (marker `browser`) that opens every page in both themes, runs prepare-release → approve through the UI, and downloads the evidence pack.
- Full suite, browser e2e and ruff green; README documents `reverseai console`.
