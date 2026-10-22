# Claude Code skills, plugins and MCP servers for building an AI multi-agent software-analysis / reimplementation platform (as of 2026-10-20)

Method note: Star counts, last-push dates, license (SPDX) and archived status were pulled live from the GitHub REST API (`api.github.com/repos/<owner>/<repo>`) on 2026-10-20. Install commands were taken from each repo's README (fetched raw from GitHub the same day) unless a different source is cited. A few repos could not be queried because the unauthenticated GitHub API rate limit ran out; they are listed under Gaps.

How plugins install in Claude Code (applies to every plugin below):
- In a session: `/plugin install <name>@<marketplace>`. This opens a details pane where you choose a scope: user, project (committed `.claude/settings.json`), or local (`.claude/settings.local.json`). Third-party marketplaces need `/plugin marketplace add owner/repo` first. — [Claude Code docs: Install and manage plugins](https://code.claude.com/docs/en/discover-plugins)
- From a shell or script: `claude plugin install <name>@<marketplace> --scope project`. On a fresh machine, run `claude plugin marketplace add anthropics/claude-plugins-official` first. Newer versions combine both steps as `claude plugin install <name> --marketplace owner/repo` (requires v2.1.292+). — [same doc](https://code.claude.com/docs/en/discover-plugins)
- Team sharing: project scope writes `enabledPlugins` to `.claude/settings.json`, which you commit. Each collaborator still runs `claude plugin install <name>@<marketplace> --scope project` once. — [same doc](https://code.claude.com/docs/en/discover-plugins)
- Auto-update is on by default for `claude-plugins-official` and off by default for third-party marketplaces. — [same doc](https://code.claude.com/docs/en/discover-plugins)
- `claude plugin details <name>` shows each plugin's always-on token cost. This matters when stacking many plugins. — [same doc](https://code.claude.com/docs/en/discover-plugins)

## 1. Spec-driven development (SDD) tooling for Claude Code

### Takeaway
Four maintained SDD frameworks have first-class Claude Code support, and all were updated within the last week: GitHub Spec Kit, OpenSpec, BMAD-METHOD and cc-sdd (Kiro-style). Superpowers is already installed and complements them: it covers brainstorm, plan and subagent-driven TDD execution, not durable spec artifacts. For a small team building a large multi-agent platform, the two clearest choices are Spec Kit (constitution, spec, plan, tasks, implement) and OpenSpec (lightweight change proposals). Use either one alongside Superpowers' execution skills.

### Cited Findings

**GitHub Spec Kit (`specify` CLI)** — https://github.com/github/spec-kit
- 142,044 stars, last push 2026-10-19, MIT, not archived. — [GitHub API](https://api.github.com/repos/github/spec-kit)
- Requirements: Python 3.11+, uv, and a supported agent. Install with `uv tool install specify-cli`, then `specify init my-project --integration <key>`. The README example uses `copilot`. — [spec-kit README](https://github.com/github/spec-kit)
- The integration key for Claude Code is `claude`, described as a "Skills-based integration; installs skills in .claude/skills". So the command is `specify init my-project --integration claude` (or `specify init . --integration claude` for an existing repo). — [Spec Kit integrations reference](https://github.github.io/spec-kit/reference/integrations.html)
- Workflow skills: `/speckit-constitution`, `/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, `/speckit-converge`. Repeat implement and converge until it reports "Converged". Clarification, checklist and analysis skills also exist. — [spec-kit README](https://github.com/github/spec-kit)
- Catalogs for extensions, presets, workflows and bundles can be searched with `specify extension search` and similar commands. The README warns that community catalog entries are not audited. — [spec-kit README](https://github.com/github/spec-kit)
- Older guides use `--ai claude` and `.claude/commands/` with dotted names like `/speckit.specify`. A 2026 PR installing v0.8.11 shows `.specify/` plus 14 `.claude/skills/speckit-*` skills. The flag name and output layout vary by version, so check `specify init --help`. — [Mintlify spec-kit init docs](https://www.mintlify.com/github/spec-kit/cli/init); [gitguardex PR #587](https://github.com/recodeee/gitguardex/pull/587)

**OpenSpec (Fission-AI)** — https://github.com/Fission-AI/OpenSpec
- 72,503 stars, last push 2026-10-19, MIT. — [GitHub API](https://api.github.com/repos/Fission-AI/OpenSpec)
- Requires Node.js 20.19.0+. Install with `npm install -g @fission-ai/openspec@latest` or `brew install openspec`, then run `openspec init` in the repo and pick Claude Code. — [OpenSpec README](https://github.com/Fission-AI/OpenSpec)
- Default commands: `/opsx:explore`, `/opsx:propose <change>`, `/opsx:apply`, `/opsx:archive`. An expanded profile adds `/opsx:new`, `/opsx:continue`, `/opsx:ff`, `/opsx:verify`, `/opsx:bulk-archive` and `/opsx:onboard`; enable it with `openspec config profile` and then `openspec update`. — [OpenSpec README](https://github.com/Fission-AI/OpenSpec)
- The README positions OpenSpec against Kiro: Kiro locks you into its IDE, while OpenSpec "works with the tools you already use". — [OpenSpec README](https://github.com/Fission-AI/OpenSpec)

**BMAD-METHOD** — https://github.com/bmad-code-org/BMAD-METHOD
- 54,355 stars, last push 2026-10-20. MIT license, though GitHub reports it as NOASSERTION; "BMad" and "BMAD-METHOD" are trademarks of BMad Code, LLC. — [GitHub API](https://api.github.com/repos/bmad-code-org/BMAD-METHOD); [BMAD README](https://github.com/bmad-code-org/BMAD-METHOD)
- Three install paths: `npx bmad-method install`, or `npx skills add bmad-code-org/BMAD-METHOD --skill '*'`, or the Claude Code plugin marketplace `/plugin marketplace add bmad-code-org/bmad-plugins`. Ask the agent for `bmad status` or `bmad setup` to check versions and apply updates. — [BMAD README](https://github.com/bmad-code-org/BMAD-METHOD)

**cc-sdd (Kiro-style specs for Claude Code)** — https://github.com/gotalab/cc-sdd
- 3,725 stars, last push 2026-10-13, MIT. — [GitHub API](https://api.github.com/repos/gotalab/cc-sdd)
- Install with `npx cc-sdd@latest`; Claude Code Skills are the default target, or pass `--claude-skills` explicitly. `--lang ja|zh-TW|es…` sets the language, `--dry-run` previews changes and `--kiro-dir docs` changes the spec directory. — [cc-sdd README](https://github.com/gotalab/cc-sdd)
- Describes itself as "Kiro-inspired": existing Kiro specs stay compatible. It ships 17 skills that cover discovery, requirements, design, tasks and autonomous implementation. — [cc-sdd README](https://github.com/gotalab/cc-sdd)
- `/kiro-impl` gives each task a fresh implementer subagent doing TDD (RED → GREEN) behind a feature flag, followed by an independent reviewer. `/kiro-spec-batch` splits a roadmap into multiple specs by dependency wave, with cross-spec review for interface mismatches. `design.md` includes a File Structure Plan, and tasks carry `_Boundary:_` and `_Depends:_` annotations. — [cc-sdd README](https://github.com/gotalab/cc-sdd)

**Superpowers (obra) — already installed** — https://github.com/obra/superpowers
- 302,384 stars, last push 2026-10-20, MIT. — [GitHub API](https://api.github.com/repos/obra/superpowers)
- Install with `/plugin install superpowers@claude-plugins-official`, or via `/plugin marketplace add obra/superpowers-marketplace` and then `/plugin install superpowers@superpowers-marketplace`. — [Superpowers README](https://github.com/obra/superpowers)
- The official marketplace lists it as teaching "brainstorming, subagent driven development with built in code review, systematic debugging…". — [claude-plugins-official marketplace.json](https://github.com/anthropics/claude-plugins-official)

**Other spec/PRD-adjacent options**
- `mattpocock-skills` in the official marketplace: "grilling, spec/ticket flows, TDD, code review, domain modelling". Install with `/plugin install mattpocock-skills@claude-plugins-official`. — [claude-plugins-official marketplace.json](https://github.com/anthropics/claude-plugins-official)
- `feature-dev` (Anthropic, official marketplace): "Comprehensive feature development workflow with specialized agents for codebase exploration, architecture design, and quality review". — [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
- Pimzino/spec-workflow-mcp is an MCP server providing SDD workflow tools: 4,300 stars, GPL-3.0, last push 2026-07-03 (less active). — [GitHub API](https://api.github.com/repos/Pimzino/spec-workflow-mcp)
- eyaltoledano/claude-task-master (PRD → tasks): 28,255 stars, last push 2026-04-28 (about 6 months stale), license NOASSERTION. — [GitHub API](https://api.github.com/repos/eyaltoledano/claude-task-master)
- trailofbits `spec-to-code-compliance` plugin: "Check code against the documentation that specifies it". This fits the reimplementation use case, where you check a clean-room implementation against the spec. — [trailofbits/skills README](https://github.com/trailofbits/skills)

### Inferences
- Spec Kit's artifact chain (constitution, spec, plan, tasks) maps naturally onto the product's clean-room "analysis, then spec, then independent reimplementation" pipeline. The team could use the same SDD discipline both for building the platform and as a model for the platform's own output format.
- Superpowers and Spec Kit/OpenSpec overlap in "plan" and "implement". A sensible split: Spec Kit or OpenSpec owns the durable spec and tasks artifacts in the repo, and Superpowers' `subagent-driven-development`, `test-driven-development` and `requesting-code-review` handle execution. Running two planners at once is likely to produce duplicate plans.
- cc-sdd's `/kiro-spec-batch` with cross-spec interface review suits a multi-service platform with many agent components.

### Gaps
- I found no authoritative head-to-head comparison of Spec Kit, OpenSpec, BMAD and cc-sdd from a neutral source.
- I could not confirm whether the current Spec Kit release still accepts `--ai claude` as an alias for `--integration claude`.

## 2. Skills marketplaces and collections relevant to agent/LLM app dev, Python/TS backend, testing, security review, docs/ADRs

### Takeaway
The official Anthropic marketplace (`claude-plugins-official`, 315 plugins, auto-registered) is the primary source. It covers Agent SDK dev (`agent-sdk-dev`), MCP server dev (`mcp-server-dev`, `mcp-apps`), LSPs (`pyright-lsp`, `typescript-lsp`), review and security (`code-review`, `pr-review-toolkit`, `security-guidance`, `claude-security`, `semgrep`), plus Context7, Playwright, GitHub, Serena, Langfuse and DeepEval. For security and reverse engineering depth, add Trail of Bits' marketplace. For language-specific skills, add `wshobson/agents`. Use the awesome lists for discovery, not as install sources.

### Cited Findings

**Anthropic official marketplace** — https://github.com/anthropics/claude-plugins-official
- 43,295 stars, last push 2026-10-20, Apache-2.0. It is added automatically the first time you start an interactive terminal session. Install with `/plugin install {plugin-name}@claude-plugins-official` or browse `/plugin > Discover`. — [GitHub API](https://api.github.com/repos/anthropics/claude-plugins-official); [README](https://github.com/anthropics/claude-plugins-official); [Claude Code docs](https://code.claude.com/docs/en/discover-plugins)
- The `marketplace.json` lists 315 plugins as of 2026-10-20. Relevant entries, quoting their descriptions: — [marketplace.json](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)
  - Agent/LLM dev: `agent-sdk-dev` ("Development kit for working with the Claude Agent SDK"); `mcp-server-dev` ("Skills for designing and building MCP servers that work seamlessly with Claude"); `mcp-apps` (MCP Apps SDK); `plugin-dev` (7 skills for building Claude Code plugins: hooks, MCP integration, commands); `skill-creator`; `huggingface-skills`; `togetherai-skills`; `atomic-agents`.
  - LLM observability and evals: `langfuse` (tracing, prompt management, evaluation skills); `langfuse-observability` (exports Claude Code traces); `deepeval` ("adding DeepEval evaluations, tracing, datasets").
  - Python/TS backend: `pyright-lsp`, `typescript-lsp`, `serena` (semantic code analysis MCP); `clangd-lsp` (useful for C/C++ decompiler output).
  - Review and testing: `code-review` (multi-agent PR review with confidence scoring); `pr-review-toolkit` (agents for comments, tests, error handling, type design); `code-simplifier`; `feature-dev`; `hookify`; `commit-commands`; `ralph-loop`; `code-modernization` (`/modernize` assessment for legacy codebases).
  - Security: `security-guidance` (pattern-based warnings on edits plus an LLM diff review on Stop); `claude-security` ("Deep vulnerability scanning of your own code, run entirely inside your Claude Code session"); `semgrep` (from semgrep/mcp-marketplace); `aikido`; `42crunch-api-security-testing`.
  - Docs and tools: `context7`, `github`, `playwright`, `chrome-devtools-mcp`, `firecrawl`, `sentry`, `linear`, `superpowers`, `mattpocock-skills`.

**anthropics/skills** — https://github.com/anthropics/skills
- 182,378 stars, last push 2026-10-09. GitHub reports no SPDX license at the repo level. — [GitHub API](https://api.github.com/repos/anthropics/skills)
- Add with `/plugin marketplace add anthropics/skills`, then `/plugin install document-skills@anthropic-agent-skills` or `example-skills@anthropic-agent-skills`. — [anthropics/skills README](https://github.com/anthropics/skills)
- Plugin groups in its marketplace.json: `document-skills` (xlsx, docx, pptx, pdf); `example-skills` (includes `mcp-builder`, `skill-creator`, `webapp-testing`, `doc-coauthoring`, `frontend-design`, …); `claude-api` (a `claude-api` skill); `academy-guide`; `discernment-nudge`. — [anthropics/skills marketplace.json](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json)

**Trail of Bits skills (security / RE)** — https://github.com/trailofbits/skills
- 7,656 stars, last push 2026-10-19, CC-BY-SA-4.0. Add with `/plugin marketplace add trailofbits/skills`, then browse with `/plugin menu`. — [GitHub API](https://api.github.com/repos/trailofbits/skills); [README](https://github.com/trailofbits/skills)
- Relevant plugins: `static-analysis` (CodeQL, Semgrep, SARIF); `differential-review`; `insecure-defaults`; `sharp-edges`; `supply-chain-risk-auditor` (npm/PyPI/Go); `variant-analysis`; `fp-check`; `semgrep-rule-creator`; `audit-context-building`; `agentic-actions-auditor` ("Audit GitHub Actions workflows for AI agent security vulnerabilities"); `trailmark` (code graph analysis, bounded subagent context slicing, Mermaid diagrams); `property-based-testing` (Hypothesis, fast-check); `mutation-testing`; `spec-to-code-compliance`; `dwarf-expert` (reverse engineering of DWARF debug info); `yara-authoring`; `firebase-apk-scanner`; `modern-python` (uv, ruff, pytest); `devcontainer-setup`; `second-opinion`. — [trailofbits/skills README](https://github.com/trailofbits/skills)

**wshobson/agents** — https://github.com/wshobson/agents
- 41,214 stars, last push 2026-10-19, MIT. Describes itself as a "multi-harness agentic plugin marketplace". — [GitHub API](https://api.github.com/repos/wshobson/agents)
- Add with `/plugin marketplace add wshobson/agents`, then for example `/plugin install python-development@claude-code-workflows`. Individual skills install with `npx skills add wshobson/agents --skill python-testing-patterns`. — [wshobson/agents README](https://github.com/wshobson/agents)

**Other collections**
- Jeffallan/claude-skills: "67 Specialized Skills for Full-Stack Developers", 11,948 stars, MIT, last push 2026-10-16. — [GitHub API](https://api.github.com/repos/Jeffallan/claude-skills)
- affaan-m/everything-claude-code (ECC) includes an `architecture-decision-records` skill: `npx skills add affaan-m/ecc --skill architecture-decision-records --agent claude-code`. A directory listing reports it as MIT; I could not verify its star count. — [claudemarketplaces.com](https://claudemarketplaces.com/skills/affaan-m/everything-claude-code/architecture-decision-records); [claudeskills.info](https://claudeskills.info/skills/affaan-m/ecc/architecture-decision-records/)
- Other ADR skills: joaquimscosta/arkhe-claude-plugins `adr` (`/adr` create, review, status, list, supersede, index; works on `docs/adr/`) and github/awesome-copilot `create-architectural-decision-record`. Both were found only through third-party directories. — [openskillindex](https://openskillindex.com/skills/joaquimscosta-arkhe-claude-plugins-adr); [claudemarketplaces.com](https://claudemarketplaces.com/skills/github/awesome-copilot/create-architectural-decision-record)
- Awesome lists, for discovery only:
  - hesreallyhim/awesome-claude-code: 56,073 stars, last push 2026-10-20. — [GitHub API](https://api.github.com/repos/hesreallyhim/awesome-claude-code)
  - ComposioHQ/awesome-claude-skills: 77,485 stars, last push 2026-09-18. — [GitHub API](https://api.github.com/repos/ComposioHQ/awesome-claude-skills)
  - travisvn/awesome-claude-skills: 15,478 stars, last push 2026-04-28 (stale). — [GitHub API](https://api.github.com/repos/travisvn/awesome-claude-skills)

**Libraries and SDKs referenced by these skills (for the product itself)**
- anthropics/claude-agent-sdk-python: 8,305 stars, MIT, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/anthropics/claude-agent-sdk-python)
- anthropics/claude-agent-sdk-typescript: 1,824 stars, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/anthropics/claude-agent-sdk-typescript)
- BerriAI/litellm: 61,642 stars, last push 2026-10-20, license NOASSERTION. Describes itself as "AI Gateway. Rust core with Python SDK. Call 100+ LLM APIs". — [GitHub API](https://api.github.com/repos/BerriAI/litellm)
- pydantic/pydantic-ai: 20,752 stars, MIT, last push 2026-10-20. — [GitHub API](https://api.github.com/repos/pydantic/pydantic-ai)
- modelcontextprotocol/python-sdk: 24,624 stars, MIT. — [GitHub API](https://api.github.com/repos/modelcontextprotocol/python-sdk)
- jlowin/fastmcp now redirects to PrefectHQ/fastmcp. — [GitHub redirect](https://github.com/jlowin/fastmcp)
- Plugins can be loaded inside the Agent SDK through its plugin option, so the same skills and plugins can ship in the product's agents. — [Claude Code docs](https://code.claude.com/docs/en/discover-plugins)

**CI / GitHub Actions**
- anthropics/claude-code-action: 9,585 stars, MIT, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/anthropics/claude-code-action)
- anthropics/claude-code-security-review (GitHub Action): 6,455 stars, MIT, last push 2026-02-11 (about 8 months, less active). — [GitHub API](https://api.github.com/repos/anthropics/claude-code-security-review)

### Inferences
- Minimum useful set for this team:
  - Official marketplace: `agent-sdk-dev`, `mcp-server-dev`, `pyright-lsp`, `typescript-lsp`, `pr-review-toolkit` or `code-review`, `security-guidance`, `context7`, `github`, `playwright`, and optionally `langfuse` and `deepeval`.
  - `anthropics/skills`: `claude-api` and `example-skills` (for `mcp-builder` and `webapp-testing`).
  - Trail of Bits: `static-analysis`, `supply-chain-risk-auditor`, `property-based-testing`, `spec-to-code-compliance`, `dwarf-expert`.
- Third-party marketplaces do not auto-update by default, so pin versions (`owner/repo#tag`) for reproducibility across the team.

### Gaps
- I found no maintained, dedicated LiteLLM or multi-provider-routing Claude Code skill or plugin, either in the official marketplace or in the sources searched. LiteLLM itself is very active, but a skill would likely have to be written in-house; `skill-creator` and `plugin-dev` help with that.
- anthropics/skills license: GitHub reports no SPDX license, and I did not verify per-skill license files.
- I could not fetch stars for affaan-m/everything-claude-code, mattpocock/skills, PrefectHQ/fastmcp or getsentry/sentry-mcp (API rate limit).

## 3. MCP servers for the product domain (RE / dynamic analysis / docs / GitHub)

### Takeaway
Mature, active MCP servers exist for every listed tool:
- Ghidra: several, with LaurieWired/GhidraMCP the most popular, plus headless options pyghidra-mcp and bethington/ghidra-mcp.
- IDA Pro: mrexodia/ida-pro-mcp, which ships its own Claude Code plugin marketplace.
- radare2: the official radareorg/radare2-mcp.
- Android: jadx-ai-mcp.
- Browser and docs: Playwright MCP, Context7 and GitHub MCP, all available as official-marketplace plugins.
- mitmproxy: only small community projects exist; this category is less mature.

Headless-capable servers (pyghidra-mcp, GhidraMCP `--headless`, bethington headless, radare2-mcp) are the ones most usable inside the product's own agent pipeline.

### Cited Findings

**Ghidra**
- **LaurieWired/GhidraMCP**: 11,428 stars, Apache-2.0, last push 2026-10-10. — [GitHub API](https://api.github.com/repos/LaurieWired/GhidraMCP)
  - Install: `claude mcp add ghidra -- uvx --from git+https://github.com/LaurieWired/GhidraMCP ghidra-mcp --ghidra-server http://127.0.0.1:8080/`
  - Headless mode: `uvx --python 3.13 --from "ghidra-mcp[headless] @ git+https://github.com/LaurieWired/GhidraMCP" ghidra-mcp --headless --binary /path/to/target`
  - Streamable-HTTP transport is also supported. — [GhidraMCP README](https://github.com/LaurieWired/GhidraMCP)
- **bethington/ghidra-mcp**: 5,810 stars, Apache-2.0, last push 2026-10-16. Describes itself as "200+ MCP tools… GUI plugin + headless server". — [GitHub API](https://api.github.com/repos/bethington/ghidra-mcp)
  - Release install: Ghidra 12.1.4, Java 21 and uv; install the Ghidra extension, then `uv tool install https://github.com/bethington/ghidra-mcp/releases/download/v7.0.0/ghidra_mcp_bridge-7.0.0-py3-none-any.whl`. — [bethington README](https://github.com/bethington/ghidra-mcp)
- **clearbluejar/pyghidra-mcp**: 449 stars, Apache-2.0, last push 2026-10-10. A Python command-line (headless) Ghidra MCP server. — [GitHub API](https://api.github.com/repos/clearbluejar/pyghidra-mcp)
  - Run with `uvx pyghidra-mcp …` or the Docker image `ghcr.io/clearbluejar/pyghidra-mcp`.
  - Claude Code over HTTP: `claude mcp add --transport http pyghidra-mcp http://127.0.0.1:8000/mcp`. — [pyghidra-mcp README](https://github.com/clearbluejar/pyghidra-mcp)
- **cyberkaida/reverse-engineering-assistant (ReVa)**: 879 stars, Apache-2.0, last push 2026-10-20. — [GitHub API](https://api.github.com/repos/cyberkaida/reverse-engineering-assistant)
  - Install: `uv tool install reverse-engineering-assistant`, then `claude mcp add --scope user ReVa -- mcp-reva`. HTTP mode: `claude mcp add --scope user --transport http ReVa -- http://localhost:8080/mcp/message`.
  - Also ships a Claude Code marketplace: `claude plugin marketplace add cyberkaida/reverse-engineering-assistant`.
  - Its design favours "smaller" tools that are easy for an LLM to use. — [ReVa README](https://github.com/cyberkaida/reverse-engineering-assistant)
- jtang613/GhidrAssistMCP now redirects to symgraph/GhidrAssistMCP. I did not check its stats. — [GitHub redirect](https://github.com/jtang613/GhidrAssistMCP)

**IDA Pro**
- **mrexodia/ida-pro-mcp**: 13,043 stars, MIT, last push 2026-09-26. — [GitHub API](https://api.github.com/repos/mrexodia/ida-pro-mcp)
  - Claude Code: `claude plugin marketplace add mrexodia/claude-marketplace`, then `claude plugin install ida-pro-mcp@mrexodia`.
  - Manual: `pip install https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip`. — [ida-pro-mcp README](https://github.com/mrexodia/ida-pro-mcp)

**Binary Ninja**
- fosdickio/binary_ninja_mcp: 456 stars, GPL-3.0, last push 2026-10-06. — [GitHub API](https://api.github.com/repos/fosdickio/binary_ninja_mcp)

**radare2**
- **radareorg/radare2-mcp (official)**: 328 stars, MIT, last push 2026-10-15. — [GitHub API](https://api.github.com/repos/radareorg/radare2-mcp)
  - Install with `r2pm -Uci r2mcp`. Configure the MCP client with command `r2pm`, args `-r r2mcp`.
  - Features: read-only mode, sandbox lock, tool restriction and fine-grained tool configuration. `r2mcp yolo on|off` toggles dangerous run tools. — [radare2-mcp README](https://github.com/radareorg/radare2-mcp)
  - The equivalent Claude Code command would be `claude mcp add r2 -- r2pm -r r2mcp`. This is my inference from the README's JSON config, not a quoted command.

**jadx (Android)**
- **zinja-coder/jadx-ai-mcp**: 2,920 stars, Apache-2.0, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/zinja-coder/jadx-ai-mcp)
  - It is a JADX plugin: download the release (`jadx-ai-plugin<version>.jar` plus the MCP server), install the plugin in jadx-gui, run `uv pip install httpx fastmcp`, then register the server in the MCP client config. The README documents Claude Desktop JSON config. — [jadx-ai-mcp README](https://github.com/zinja-coder/jadx-ai-mcp)

**Frida (dynamic instrumentation)**
- dnakov/frida-mcp (Python, MIT): process listing, attach, spawn and kill, a JS REPL and script injection. nonsleepr/frida-mcp.ts (TypeScript/Bun, frida ^17). Both found only through directory listings; I did not verify stars or activity. — [Glama dnakov/frida-mcp](https://glama.ai/mcp/servers/@dnakov/frida-mcp/blob/f8003c7de69ca8fc13a019f0c9b6abcc61b1717c/README.md); [Glama nonsleepr/frida-mcp.ts](https://glama.ai/mcp/servers/@nonsleepr/frida-mcp.ts/blob/278e549df5ab6084015c7b21a727752dc29e438f/package.json)

**mitmproxy (traffic interception)**
- **snapspecter/mitmproxy-mcp**: 130 stars, MIT, last push 2026-09-28. "Wraps mitmproxy and exposes it as a tool… inspect, modify, and replay HTTP/HTTPS traffic". — [GitHub API](https://api.github.com/repos/snapspecter/mitmproxy-mcp); [README](https://github.com/snapspecter/mitmproxy-mcp)
  - Install with `uv tool install mitmproxy-mcp` or `pip install mitmproxy-mcp`. Needs the proxy configured, usually at localhost:8080, and the mitmproxy CA certificate installed. — [README](https://github.com/snapspecter/mitmproxy-mcp)
- moha-abdi/mitmproxy-mcp runs as a mitmproxy addon with 24 tools and redacts tokens, passwords and JWTs before data reaches the model. mplogas/mitm-mcp targets IoT. Both found only through directories. — [Glama moha-abdi](https://glama.ai/mcp/servers/moha-abdi/mitmproxy-mcp)

**Playwright**
- **microsoft/playwright-mcp**: 38,400 stars, Apache-2.0, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/microsoft/playwright-mcp)
  - Install: `claude mcp add playwright npx @playwright/mcp@latest`. It also exists as the official-marketplace plugin `playwright`. — [playwright-mcp README](https://github.com/microsoft/playwright-mcp); [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
- `chrome-devtools-mcp` (official marketplace) records performance traces and analyzes network requests in a live Chrome. — [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

**Context7 (docs)**
- **upstash/context7**: 63,349 stars, MIT, last push 2026-10-20. — [GitHub API](https://api.github.com/repos/upstash/context7)
  - Install: `npx ctx7 setup --claude` (Node 22.13+). It handles OAuth and the API key, and offers either "CLI + Skills" mode or MCP mode.
  - Manual: remote MCP at `https://mcp.context7.com/mcp` with an `Authorization: Bearer` header. — [context7 README](https://github.com/upstash/context7)
  - Also available as the official-marketplace plugin `context7`, which uses the hosted remote server. — [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

**GitHub MCP**
- **github/github-mcp-server**: 33,789 stars, MIT, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/github/github-mcp-server)
  - Remote endpoint: `https://api.githubcopilot.com/mcp/`.
  - Local: `claude mcp add github -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PAT -- docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server`. — [github-mcp-server README](https://github.com/github/github-mcp-server)
  - Also the official-marketplace plugin `github`. — [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

**Code navigation**
- **oraios/serena**: 30,438 stars, last push 2026-10-20, license NOASSERTION. Semantic retrieval and editing over a language server; install with `uv tool install -p 3.13 serena-agent`. Also the official-marketplace plugin `serena`. — [GitHub API](https://api.github.com/repos/oraios/serena); [serena README](https://github.com/oraios/serena); [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

**Static analysis MCP**
- semgrep/mcp is archived (last push 2025-10-28). Use the official-marketplace `semgrep` plugin from semgrep/mcp-marketplace instead. — [GitHub API](https://api.github.com/repos/semgrep/mcp); [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

**Reference servers**
- modelcontextprotocol/servers: 91,404 stars, last push 2026-10-19. — [GitHub API](https://api.github.com/repos/modelcontextprotocol/servers)

### Inferences
- For use *inside the product* (automated, multi-agent, server-side), prefer headless, HTTP-transport servers that can run in containers: pyghidra-mcp (Docker image), GhidraMCP `--headless`, bethington headless, radare2-mcp (sandbox and read-only flags), and ReVa (HTTP mode). GUI-bound servers (jadx-ai-mcp, IDA Pro MCP, which needs a commercial IDA licence) suit analyst-assist and development work better than unattended pipelines.
- radare2-mcp's read-only and sandbox modes and moha-abdi/mitmproxy-mcp's secret redaction are relevant guardrail patterns for the platform's own tool layer.
- MCP servers on the RE side can feed analysis output into a spec. Trail of Bits `spec-to-code-compliance` and Spec Kit's `converge` can then check the reimplementation against that spec, which closes the clean-room loop.

### Gaps
- Exact current stars and activity for the Frida MCP servers, moha-abdi/mitmproxy-mcp, mplogas/mitm-mcp and symgraph/GhidrAssistMCP are unverified (API rate limit, or found only through directories).
- I found no Claude Code-specific `claude mcp add` command in the jadx-ai-mcp or radare2-mcp READMEs; both document Claude Desktop JSON config.
- I did not evaluate the quality or security of community MCP servers. Review their code before use, since MCP servers run with local privileges ([Claude Code plugin security](https://code.claude.com/docs/en/discover-plugins)).
