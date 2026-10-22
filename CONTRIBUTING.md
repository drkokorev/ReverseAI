# Contributing

ReverseAI is a research prototype that is not actively developed. Forks are the expected way to take it further; pull requests are welcome, but reviews may be slow.

## Getting started

```bash
uv sync
uv run playwright install chromium
uv run pytest                        # default run excludes `live`
uv run pytest -m browser tests/e2e   # the whole pipeline on the demo target, LLM scripted
uv run ruff check src tests
```

Read these first:

- [`CLAUDE.md`](CLAUDE.md) — architecture map and the hard rules (zones, barrier, ledger, black-box only). They apply to human contributors as much as to coding agents.
- [`docs/spec/decisions.md`](docs/spec/decisions.md) — why things are the way they are. Record a new decision there (next free `D-NNN`) if your change sets one.

## Ground rules

- Keep the clean-room guarantees intact: clean-zone code reads only released artifacts through `ArtifactStore`, all LLM calls go through `Gateway`, and nothing from the original (code, page text, brand) crosses the barrier unsanitized.
- No decompiling or parsing of target code for logic — black box only.
- No API keys in code, tests, the ledger or fixtures.
- User-facing strings go through the i18n catalogs (`src/reverseai/i18n/en.py` and `ru.py`).
- Add tests for the behavior you change; keep `pytest` and `ruff` green.

## Good places to start

See "Status and help wanted" in the [README](README.md#status-and-help-wanted): a live benchmark run, Docker isolation in the CLI, a real open-source target, login flows, a TypeScript clone template, model cost comparisons.

## Responsible use

Contributions that make the tool easier to use against products you have no right to analyze, or that weaken the barrier, will not be merged. See [Responsible use](README.md#responsible-use).
