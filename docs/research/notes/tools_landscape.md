# Landscape: AI-assisted software analysis and clean-room reimplementation tools (as of 20 Oct 2026)

Research date: 2026-10-20. Star counts change quickly. Each figure below carries the date of its snapshot. Where sources disagree, both values are given.

## 1. Notable 2025-2026 public projects where AI agents rebuilt known software (incl. the viral "open-source Adobe" project)

### Takeaway
The viral project is **ArtCraft** by Brandon Thomas (Storyteller.ai, ex-Square): seven pure-Rust "clean-room reimplementations" of Adobe apps, built mainly with Claude Opus 5.5 using several agents in parallel, and launched on GitHub in early October 2026. The flagship repo is `storytold/photocraft`, with about 69k stars by 20 Oct 2026. It describes itself as early alpha, and only about 2 of the 7 apps are called usable. Other reference cases from 2025-2026 are chardet 7.0 (an LGPL-to-MIT rewrite with Claude Code), Malus.sh ("clean room as a service"), Anthropic's 16-agent C compiler, Cursor's FastRender browser, claw-code (a rewrite of the leaked Claude Code), and conformance-suite-driven ports such as JustHTML.

### Cited Findings
**ArtCraft / PhotoCraft (Adobe suite alternative), Oct 2026**
- Who and what: Brandon Thomas, formerly CEO of Storyteller.ai and an engineer at Square, built seven free open-source Adobe alternatives in Rust with Claude as his coding assistant. The apps and their Adobe counterparts are PhotoCraft (Photoshop), VectorCraft (Illustrator), FilmCraft (Premiere), LightCraft (Lightroom), PrintCraft/PdfCraft (Acrobat), EffectCraft (After Effects) and DesignCraft (InDesign). — [ProPakistani, 2026-10-09](https://propakistani.pk/2026/10/09/free-open-source-copies-of-photoshop-premiere-and-lightroom-are-here/); [Notebookcheck](https://notebookcheck.net/Photoshop-Premiere-more-Experienced-Rust-developer-recreates-Adobe-suite-with-AI-assistance-as-open-source.1419230.0.html)
- How it was built: pure Rust over "a few days" using Claude Opus 5.5. Thomas said multiple parallel Opus 5.5 agents were used to implement menus and functionality quickly. Launched on GitHub in early October 2026. — [TechRepublic](https://www.techrepublic.com/article/news-developer-ai-free-adobe-creative-cloud-alternatives/) (page returned 403, so this comes from the search snippet); [Dapta summary](https://dapta.ai/blog-posts/ai-news-adobe-clone/)
- Stack: native on macOS, Windows and Linux (plus FreeBSD per the README), with most apps also running in the browser via WebAssembly. The UI uses egui and wgpu. — [ProPakistani](https://propakistani.pk/2026/10/09/free-open-source-copies-of-photoshop-premiere-and-lightroom-are-here/); [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Tom's Hardware headline: "Solo developer rebuilds Adobe Creative Suite in Rust using Claude, releases it free to all — targets 100% parity in one month despite piracy claims and safety warnings". — [Tom's Hardware](https://www.tomshardware.com/software/video-editing-graphic-design/solo-developer-rebuilds-adobe-creative-suite-in-rust-using-claude-releases-it-free-to-all-targets-100-percent-parity-in-one-month-despite-piracy-claims-and-safety-warnings)
- Repo facts: `storytold/photocraft` was created 2026-09-30. It is dual-licensed MIT OR Apache-2.0 (the GitHub API reports Apache-2.0). It had **69,072 stars** in a GitHub search API snapshot on 2026-10-20. — [GitHub](https://github.com/storytold/photocraft). Earlier press figures were about 43,000 ([LinuxCompatible](https://www.linuxcompatible.org/story/artcraft-the-free-opensource-adobe-suite-that-racked-up-43000-stars-in-days/)) and 44,238 on 2026-10-11 ([ProPakistani](https://propakistani.pk/2026/10/09/free-open-source-copies-of-photoshop-premiere-and-lightroom-are-here/)).
- Clean-room claims in the README:
  - The PSD crate is "written from Adobe's public specification".
  - "No proprietary code, shaders or assets."
  - The UI is laid out so that Photoshop users find things where they expect them.
  - There is a non-affiliation disclaimer, and the ArtCraft trademarks are excluded from the license.

  The README does not describe how AI was used. — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Verification approach in the README, which is the most useful part for platform design:
  - Photoshop-authored "oracle" PSDs, plus the psd-tools, ag-psd and PngSuite corpora, all pinned and sha256-verified. A separate corpus repo exists: `storytold/photocraft-corpus` (created 2026-10-05).
  - Round-trip results: 307/309 psd-tools files re-save with the same render.
  - Renders are compared against Photoshop's own merged composite image.
  - The CPU compositor is the reference, and the GPU compositor is cross-checked against it.
  - 116/116 shape layers in the corpus match Photoshop's pixels.
  - More than 1,700 tests, plus fuzzing.

  — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Agent-drivable design: every action is a command in one registry of more than 500 commands, exposed through an MCP server, a CLI and a JSON control channel. The repo has an AGENTS.md. A third-party repo already packages agent skills for the suite (`midasmatterhorn/artcraft-skills`, created 2026-10-14). — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Self-assessed maturity: "early alpha", and "not yet a Photoshop replacement for daily professional work". Gaps include generative AI features, 15 missing tools, typography depth and plug-in compatibility. Menu wiring for every Photoshop item "measures wiring, not behaviour". — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Reviewers found PhotoCraft has 67 tools and PSD support but no Generative Fill. Only 2 of the 7 apps are genuinely usable. Legal experts flag trade-dress and patent risks. The project is funded by an optional paid AI studio (getartcraft.com credits). — [LinuxCompatible](https://www.linuxcompatible.org/story/artcraft-the-free-opensource-adobe-suite-that-racked-up-43000-stars-in-days/); [BigGo](https://finance.biggo.com/news/73561259-ed7b-4ea5-800d-cadb1acafcff); [daily.dev hands-on](https://daily.dev/posts/i-tried-replacing-photoshop-lightroom-and-acrobat-with-free-vibe-coded-alternatives-and-they-re-s-1reeeglht)
- Commenters were skeptical about whether the Photoshop reimplementation is truly "clean-room". — [daily.dev](https://daily.dev/posts/an-open-source-clean-room-reimplementation-of-adobe-photoshop-in-pure-rust-3v5pxq1kg)

**chardet 7.0 (Mar 2026): Claude Code rewrite with relicensing**
- Around 2026-03-03, maintainer Dan Blanchard released chardet 7.0.0, a "ground-up, MIT-licensed rewrite" with the same package name and API. Process:
  1. He used the superpowers brainstorming skill to write a design doc.
  2. He worked in an empty repo, without the old source tree, and told Claude not to base anything on LGPL/GPL code.
  3. The plan doc is dated 2026-02-25 and starts with tests.

  — [Simon Willison, 2026-03-05](https://simonwillison.net/2026/Mar/5/chardet/)
- On 2026-03-04 original author Mark Pilgrim opened issue #327, "No right to relicense this project". Blanchard acknowledged there was no human separation between the person with knowledge of the original and the implementer. He cited JPlag similarity of 1.29% against the previous release, versus 80-93% between other releases. Claude Code read `metadata/charsets.py` from the original once. Richard Fontana (co-author of LGPLv3) said on 2026-03-27 that he saw no basis so far for requiring the LGPL. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)

**Malus.sh: "clean room as a service" (FOSDEM 2026, ~Feb-Mar 2026)**
- Presented by Dylan Ayrey and Mike Nolan at FOSDEM 2026. It is satire, but also a real, revenue-generating LLC. The user uploads a dependency manifest. AI agents then generate specifications from public documentation, and a separate agent recreates functionally equivalent code without the original licenses. Nolan: "It works." — [404 Media](https://www.404media.co/this-ai-tool-rips-off-open-source-software-without-violating-copyright/); [Gigazine, 2026-03-13](https://www.gigazine.net/gsc_news/en/20260313-malus-open-source/); [LetsDataScience](https://letsdatascience.com/news/malus-provides-clean-room-recreated-open-source-code-6edac75b); [Elektroda](https://www.elektroda.com/news/news4169248.html)
- Main criticism: the "clean room" is weak because the LLM has already ingested the open-source corpus. This is commenter opinion, not a legal ruling. — [LetsDataScience](https://letsdatascience.com/news/malus-provides-clean-room-recreated-open-source-code-6edac75b)

**claw-code (Apr 2026): rewrite of the leaked Claude Code agent**
- On 2026-03-31, Claude Code v2.1.88 shipped to npm with a source map exposing about 512k lines of TypeScript. GitHub disabled more than 8,100 repos after DMCA notices. Sigrid Jin used OpenAI Codex to rewrite the core agent architecture in Python as "claw-code", reportedly within hours, and it was framed as a clean-room reimplementation. Reported stars range from 30k to over 100k. — [heise](https://heise.de/en/news/Claude-Code-Leak-8100-Takedown-Requests-and-the-Birth-of-Claw-Code-11279674.html); [IPKat, Apr 2026](https://ipkitten.blogspot.com/2026/04/the-claude-code-leak-that-spurred-8100.html?hl=en); [Decrypt](https://decrypt.co/362917/anthropic-accidentally-leaked-claude-code-source-internet-keeping-it-forever?amp=1)
- Related essay: "The Code That Nobody Owns". — [Medium, Marc Bara](https://medium.com/@marc.bara.iniesta/the-code-that-nobody-owns-52d569332f5e)

**Anthropic, "Building a C compiler with a team of parallel Claudes" (Feb 2026)**
- Nicholas Carlini ran 16 Claude Opus 4.6 agents across about 2,000 Claude Code sessions, costing about $20k in API fees. They produced a roughly 100k-line Rust C compiler that builds Linux 6.9 on x86, ARM and RISC-V, in about 2 weeks. — [Anthropic Engineering](https://www.anthropic.com/engineering/building-c-compiler); [InfoQ, Feb 2026](https://www.infoq.com/news/2026/02/claude-built-c-compiler/); [OfficeChai](https://officechai.com/ai/anthropic-says-that-16-instances-of-claude-opus-4-6-working-in-parallel-autonomously-built-a-c-compiler-in-2-weeks/)

**Cursor FastRender (Jan 2026)**
- Wilson Lin at Cursor had thousands of agents build a browser engine in Rust with GPT-5.2. It ran for about a week and produced more than 1,000 files and over 1M LOC (the CEO later said more than 3M). — [Simon Willison, 2026-01-19](https://simonwillison.net/2026/Jan/19/scaling-long-running-autonomous-coding/); [Simon Willison interview, 2026-01-23](https://simonwillison.net/2026/Jan/23/fastrender/)
- Critics said it barely compiled, CI was failing and there were no build instructions at launch. — [The Register, 2026-01-26](https://theregister.com/2026/01/26/cursor_opinion); [R&D World](https://www.rdworldonline.com/?p=81571)

**JustHTML ports (Dec 2025)**
- Emil Stenström built the Python JustHTML parser with agents against the html5lib-tests suite. Simon Willison ported it to JavaScript (`simonw/justjshtml`) with Codex CLI and GPT-5.2 in about 4.5 hours with 2 main prompts, and it passes 9,200 html5lib tests. Anil Madhavapeddy then ported it to OCaml (html5rw), which he called "vibespiling". — [Simon Willison, 2025-12-15](https://simonwillison.net/2025/Dec/15/porting-justhtml/); [Simon Willison, 2025-12-17](https://simonwillison.net/2025/Dec/17/vibespiling/)

**Directory of such projects**
- GitHub topic `clean-room-reimplementation`, plus a community directory of "independently recreated software" that lists several Claude Code reimplementation projects. — [GitHub topic](https://github.com/topics/clean-room-reimplementation)

### Inferences
- The successful projects share three traits:
  - The target has a **public spec or format** (Adobe PSD spec, C standard, HTML5 spec).
  - There is an **oracle**: GCC, Photoshop-exported composites, html5lib-tests.
  - There is **massive parallel agent effort**.

  A commercial platform should treat "find or build the oracle and corpus" as the first-class product step.
- PhotoCraft's "menu wiring ≠ behaviour" admission shows that UI-surface parity is cheap with agents and behavioural parity is the hard part. Parity metrics should be oracle-based, not feature-checklist-based.
- The legal framing is still unsettled. chardet, Malus and claw-code show that "AI clean room" claims are contested on two grounds: agents have exposure to the original, and model training data includes it. A platform needs provable information barriers (logging what each agent saw) and similarity reports (JPlag-style) as auditable artifacts.

### Gaps
- The exact viral article: TechRepublic and Tom's Hardware returned 403 or truncated pages. The details of Thomas's agent workflow (number of agents, spec docs, whether he used Claude Code) could not be confirmed from primary text. The PhotoCraft README is silent on AI usage.
- The Acrobat clone is named "PrintCraft" in the press but "PdfCraft" in the README.
- The claw-code repo URL and star count could not be verified (the GitHub API was rate-limited).

## 2. Methodology: spec extraction, test-first conformance, multi-agent separation, verification loops

### Takeaway
The working recipe is a four-step pipeline:
1. Extract a spec (from docs, public format specs, or observed runtime behaviour).
2. Assemble or generate a conformance and oracle test suite before implementation.
3. Separate spec-writer agents from implementer agents.
4. Run long, parallel implement-test loops with fast, low-noise test harnesses and a differential oracle.

The test suite matters more than the agent framework.

### Cited Findings
- Malus pipeline: one set of agents produces high-level specifications from public documentation, and a **separate** agent writes the implementation, mirroring the human two-team clean room (Phoenix/IBM BIOS). — [404 Media](https://www.404media.co/this-ai-tool-rips-off-open-source-software-without-violating-copyright/); [Elektroda](https://www.elektroda.com/news/news4169248.html)
- Legal commentary: agent separation is "architectural" rather than the human separation courts have recognised, and no court has ruled on AI clean rooms. Precedents (Phoenix/IBM, Sega v. Accolade) all involved humans. — [Matt Hopkins](https://matthopkins.com/technology/clean-room-loophole-agentic-coding-software-copyright/); [agenticthinking.ai "The Clean Room"](https://agenticthinking.ai/blog/the-clean-room/)
- chardet process: design doc first (brainstorming skill), then an empty repo, an explicit instruction not to use LGPL/GPL code, a plan that starts with tests, and finally JPlag similarity measurement as evidence of independence. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)
- Carlini's C compiler, how the agents were organised:
  - Each agent ran in its own Docker container.
  - Coordination went through git: agents claimed tasks via lock files, and there was no master orchestrator.
- Carlini's C compiler, key lessons:
  - Test design mattered most.
  - Keep test output terse to save context.
  - Fast test modes sample 1-10% of cases.
  - When all agents got stuck on the same kernel bug, GCC served as a known-good **oracle**: compile most files with GCC and a subset with the new compiler to bisect.
  - New features frequently broke old ones.
  - The project "nearly reached the limits" of Opus.

  — [InfoQ](https://www.infoq.com/news/2026/02/claude-built-c-compiler/); [BetterStack guide](https://betterstack.com/community/guides/ai/anthropic-ai-agents-c-compiler/)
- Cursor FastRender architecture: planners and sub-planners create tasks, workers execute them, and a judge agent decides whether the project is complete at the end of each cycle. Rigid up-front planning proved too brittle, so they moved to dynamic task selection. A browser was chosen because it is "extremely ambitious and complex but also well specified". Willison's view: "the cheat code is the conformance suites". — [Simon Willison](https://simonwillison.net/2026/Jan/19/scaling-long-running-autonomous-coding/); [Simon Willison interview](https://simonwillison.net/2026/Jan/23/fastrender/)
- JustHTML: the html5lib-tests conformance suite (9,200 tests) was hooked in "almost from the start". Willison calls this "vibe engineering", where the test suite is the main safeguard. — [Simon Willison](https://simonwillison.net/2025/Dec/15/porting-justhtml/)
- PhotoCraft verification stack: pinned third-party corpora, an oracle of the original app's own exported output, and a CPU reference compositor cross-checked against the GPU compositor. — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- Behaviour-capture approach in industry: Mechanical Orchard's Imogen builds a **behavioural specification from the running system**, covering data couplings, scheduler dependencies and load behaviour. It replicates production data flows synthetically and runs a closed loop of code generation and verification against that spec. Since the Summer 2026 release (2026-07-09) it integrates with AWS Transform, which handles business-rule extraction. — [Mechanical Orchard press release](https://www.mechanical-orchard.com/insights/mechanical-orchard-releases-imogen-platform-improvements); [Mechanical Orchard platform](https://www.mechanical-orchard.com/platform)
- Spec-driven development tooling:
  - GitHub Spec Kit is an MIT-licensed CLI, open-sourced around Sep 2025. Stars: 72k+ (Apr 2026) to 115k (Jun 2026). It is criticised for process weight.
  - AWS Kiro is an IDE, CLI and web app that turns prompts into specs, designs and task lists.
  - Others in the category are OpenSpec, Tessl and BMAD-METHOD.

  — [codemyspec](https://codemyspec.com/blog/spec-kit-vs-kiro); [SSOJet](https://ssojet.com/blog/best-spec-driven-development-tools); [Medium guide](https://medium.com/@visrow/comprehensive-guide-to-spec-driven-development-kiro-github-spec-kit-and-bmad-method-5d28ff61b9b1)

### Inferences
- Proposed platform pipeline:
  1. **Observation agents** (UI, network and binary tools; see section 3) produce behavioural traces.
  2. **Spec agents** distil the traces into a spec and executable conformance tests.
  3. A **firewalled implementer** sees only the spec and tests.
  4. A **differential verifier** replays the same inputs against the original app and the clone.

  Mechanical Orchard's Imogen is the closest commercial analogue for the behaviour-capture-to-verification loop, though it targets mainframes only.
- Fast, terse test harnesses and a known-good oracle are what let long-running agent swarms converge. Without them, regressions dominate (Carlini).

### Gaps
- I found no published head-to-head evaluation of spec-writer/implementer separation versus a single agent in terms of output quality or independence.
- There is no detailed public description of Malus's internal agent architecture beyond the press summaries.

## 3. Program analysis tooling with LLM/MCP integrations

### Takeaway
MCP bridges now exist for every major RE tool:
- IDA: the community `ida-pro-mcp` (~13k★) and an official Hex-Rays `ida-mcp`.
- Ghidra: `GhidraMCP` (~11k★) and `bethington/ghidra-mcp` with 200+ tools.
- Binary Ninja: an MCP server plus the commercial Sidekick.
- radare2: the official r2mcp.
- jadx: `jadx-ai-mcp`.

They are mostly MIT or Apache-2.0, so a platform can embed them. For UI behaviour capture, Microsoft's Playwright MCP (~38k★, Apache-2.0) is the standard. I could not verify mature Frida or mitmproxy MCP servers in this pass.

### Cited Findings
Comparison of RE MCP servers (snapshot 2026-10-17) — [DEV.to comparison, 2026-10-17](https://dev.to/leemie8848/ai-reverse-engineering-tools-compared-rea-ida-mcp-ghidramcp-and-friends-oct-2026-3hfl):

| Tool | URL | Stars (2026-10-17) | License | Notes |
|---|---|---|---|---|
| ida-pro-mcp (mrexodia) | https://github.com/mrexodia/ida-pro-mcp | ~13.0k | MIT | IDA Pro 8.3+ (9 recommended); IDA Free not supported; mature and widely used; last push 2026-09-26 |
| Hex-Rays official IDA MCP | https://github.com/HexRaysSA/ida-mcp | ~1.2k | MIT | Vendor-maintained; IDA 9.4+, idalib, Python 3.11+; last push 2026-10-08 |
| GhidraMCP (LaurieWired) | https://github.com/LaurieWired/GhidraMCP | ~11.3k | Apache-2.0 | Ghidra plugin plus Python MCP bridge; native binaries only; Ghidra 12.1.4 |
| ghidra-mcp (bethington) | https://github.com/bethington/ghidra-mcp | ~5.7k | Apache-2.0 | 200+ tools; GUI plugin plus headless/Docker/CI mode |
| pyghidra-mcp (clearbluejar) | https://github.com/clearbluejar/pyghidra-mcp | ~450 | Apache-2.0 | Headless-first, good for automation |
| REA (morluto) | https://github.com/morluto/rea | reported "~296k" (implausible; verify) | MIT | Drives Hopper, Ghidra or IDA; also handles JS/Electron, .NET, websites and Android; fast-moving |

- The star counts above should be checked against GitHub. One source puts GhidraMCP at 5.4k+ and another at 11.3k. — [Enterprise DNA directory](https://enterprisedna.co/directories/mcp/lauriewired-ghidramcp/); [DEV.to](https://dev.to/leemie8848/ai-reverse-engineering-tools-compared-rea-ida-mcp-ghidramcp-and-friends-oct-2026-3hfl)
- REA vendor comparison page (biased source). — [rea-reverse.com](https://rea-reverse.com/en/rea-vs-ghidramcp-ida-pro-mcp/)
- `jtsylve/re-mcp`: a headless MCP server for both IDA Pro and Ghidra. — [GitHub](https://github.com/jtsylve/re-mcp)
- Curated list of RE tools with MCP servers. — [crowdere/Awesome-RE-MCP](https://github.com/crowdere/Awesome-RE-MCP)
- Other IDA MCP variants:
  - blacktop/ida-mcp-rs tracks IDA versions, with v9.4.x and a 9.5-beta prerelease.
  - IDAssistMCP.
  - IDA Auto MCP (headless, idalib, multi-binary).
  - 31Benzi IDA Pro MCP (87 tools, IDA 9.0+).

  — [blacktop wiki](https://github.com/blacktop/ida-mcp-rs/wiki); [Glama listing](https://glama.ai/mcp/servers/mufeng05/ida-auto-mcp)
- Binary Ninja MCP (fosdickio) is the most-referenced community plugin. It covers decompilation, HLIL/MLIL/LLIL, renaming, types, xrefs, strings, patching and multiple open binaries. — [Awesome-RE-MCP](https://github.com/crowdere/Awesome-RE-MCP); [claudemarketplaces RE category](https://claudemarketplaces.com/mcp/category/reverse-engineering)
- radare2: the official `radareorg/radare2-mcp` (r2mcp, stdio) had about 328★ and 40 forks in one snapshot (321★ in another). Do not confuse it with the `drvcvt/radare2-mcp` fork (85 tools, 2★). — [GitHub radareorg/radare2-mcp](https://github.com/radareorg/radare2-mcp); [drvcvt](https://github.com/drvcvt/radare2-mcp)
- jadx (Android/Java): the `zinja-coder/jadx-ai-mcp` plugin had about 2.9k★ and the companion `jadx-mcp-server` about 803★ (snapshot dates unclear). — [jadx-ai-mcp](https://github.com/zinja-coder/jadx-ai-mcp); [jadx-mcp-server](https://github.com/zinja-coder/jadx-mcp-server)
- Cisco Talos describes using LLMs as an RE "sidekick" via MCP. — [Talos blog](https://blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/)
- Playwright MCP (Microsoft): Apache-2.0, about 38.4k★ (other snapshots show 36.7k). It drives a real browser through **accessibility snapshots rather than screenshots**, and works with Claude Code, Codex, Cursor and Copilot. Microsoft now points coding agents to Playwright CLI plus Skills instead of MCP because the tool schemas cost too much context. — [GitHub microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp); [Oodle guide, 2026](https://www.oodle.ai/guides/mcp/playwright)
- PhotoCraft itself exposes an MCP server, a CLI and a JSON control channel over a 500+ command registry. This is an example of the reimplementation being made agent-testable. — [GitHub storytold/photocraft](https://github.com/storytold/photocraft)

### Inferences
- Coverage differs by target type:
  - Native binaries: well served (IDA, Ghidra, Binary Ninja, r2), with permissive licenses suitable for embedding.
  - Android: jadx.
  - Web apps: Playwright.
  - Desktop GUI apps: weaker, relying on computer-use and accessibility APIs.
  - Network/API traffic: no clear MCP leader found.
- Headless modes (pyghidra-mcp, bethington's Docker mode, idalib-based IDA servers) matter for a cloud SaaS platform. IDA-based options carry per-seat licensing costs. Ghidra-based ones are free.
- For a "clean-room" platform, decompilation tools are legally sensitive. Most relevant precedent (Sega v. Accolade) allows disassembly for interoperability, but output from these tools should feed only the spec side, never the implementer.

### Gaps
- Frida MCP, mitmproxy MCP and HAR-to-OpenAPI LLM tools: searches returned nothing reliable. These need a dedicated pass (candidates to check include frida-mcp variants, mitmproxy2swagger, and Burp Suite AI features).
- The Binary Ninja MCP (fosdickio) star count and license were not confirmed.
- The REA "~296k stars" figure from DEV.to looks erroneous. The GitHub API was rate-limited, so it could not be verified.
- Computer-use agents for desktop UI exploration (Anthropic computer use, OpenAI Operator/CUA) were not covered in this pass.

## 4. Commercial products and startups in adjacent spaces (pricing where available)

### Takeaway
- RE vendors are adding AI with explicit price tiers: Binary Ninja Sidekick at $24-$300/month or $5k/user/year self-hosted, and RevEng.AI, which raised a $15M Series A in May 2026 and does not publish prices.
- Legacy modernization is converging on behaviour-capture plus verification: Mechanical Orchard Imogen integrated with AWS Transform, alongside IBM watsonx Code Assistant and Amazon Q migration.
- Spec-driven tooling (Kiro, Spec Kit) is the generic substrate.

### Cited Findings
- **Binary Ninja Sidekick** (Vector 35):
  - Free tier for users with active Binary Ninja support, with monthly credits.
  - Basic: $30/mo ($24/mo annual).
  - Pro: $100/mo ($80/mo annual).
  - Max: $300/mo ($240/mo annual).
  - Self-hosted: $5,000 per concurrent user per year, minimum 3 licenses.
  - All plans have the same capabilities and differ only in usage limits and data-collection terms.

  — [Sidekick pricing](https://sidekick.binary.ninja/pricing/); [Introducing Sidekick Free](https://sidekick.binary.ninja/blog/introducing-sidekick-free/)
- **Binary Ninja 6.0 "Krypton"** (2026-09-03): new pricing. Non-commercial dropped from $299 to $199, and Commercial is $1,799. — [Binary Ninja blog](https://binary.ninja/2026/09/03/binary-ninja-6.0-krypton.html); [Binary Ninja purchase](https://binary.ninja/purchase/)
- **RevEng.AI** (London):
  - Raised a $15M Series A in late May 2026, led by the NATO Innovation Fund with Sands Capital, In-Q-Tel, IQ Capital and Episode One. Total funding is about $19.15M per Caplight.
  - Its "BinNet" model analyses binaries, firmware and third-party software without source code, looking for vulnerabilities, backdoors and supply-chain anomalies.
  - Headcount grew from 16 to 26.
  - Pricing is subscription-based with tiers, but no public price list was found.

  — [IQ Capital](https://iqcapital.vc/news/reveng-ai-raises-15m-to-secure-ai-generated-software); [SecurityBrief](https://securitybrief.co.uk/story/reveng-ai-raises-usd-15-million-to-secure-software); [Caplight](https://www.caplight.com/company/reveng); [Preqin](https://www.preqin.com/data/profile/asset/reveng-ai/750585)
- **Hex-Rays**: an official MCP server (`HexRaysSA/ida-mcp`, MIT, IDA 9.4+) exists per the DEV.to snapshot. I found no official Hex-Rays announcement of native AI features. — [DEV.to](https://dev.to/leemie8848/ai-reverse-engineering-tools-compared-rea-ida-mcp-ghidramcp-and-friends-oct-2026-3hfl)
- **REA**: positioned as a free alternative to Binary Ninja Sidekick that still needs an existing decompiler. — [Artificially Intimidating](https://artificiallyintimidating.com/p/rea)
- **Mechanical Orchard (Imogen)**:
  - Mainframe modernization from observed behaviour: CICS, COBOL, DB2, JCL, MQ, z/OS.
  - Summer 2026 release (2026-07-09) adds AWS Transform integration and a new build pipeline.
  - Partners with Leidos (US federal) and Thoughtworks, which claims a case went from an 18-month plan to 5 months (a vendor claim).
  - Listed on AWS Marketplace.

  — [Mechanical Orchard](https://www.mechanical-orchard.com/insights/mechanical-orchard-releases-imogen-platform-improvements); [Thoughtworks partner page](https://www.thoughtworks.com/en-au/about-us/partnerships/technology/mechanical-orchard); [AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-tcry42kis5gxq)
- **Migration players** named by a 2026 enterprise fundraising guide (secondary, unverified source): IBM watsonx Code Assistant (COBOL→Java), Amazon Q migration (Java 8→21), and Mechanical Orchard. — [startupfundraising.com](https://startupfundraising.com/ai-coding-agents-enterprise-fundraising)
- **Malus.sh**: a commercial "clean-room-as-a-service" LLC that recreates OSS dependencies from a manifest. Price not found. — [404 Media](https://www.404media.co/this-ai-tool-rips-off-open-source-software-without-violating-copyright/)
- **Spec-driven tools**: AWS Kiro (commercial IDE, CLI and web) and GitHub Spec Kit (MIT). — [codemyspec](https://codemyspec.com/blog/spec-kit-vs-kiro)
- Funding context: AI startups took $102B, or 64% of global VC, in Q3 2026. — [Crunchbase News](https://news.crunchbase.com/venture/q3-2026-global-startup-funding-ai-billion-dollar-rounds-exits-data/)

### Inferences
- No direct commercial competitor was found offering "observe any app, then produce an independent equivalent implementation" as a general product.
  - Malus targets OSS dependencies from docs.
  - Mechanical Orchard targets mainframes from runtime capture.
  - RevEng.AI targets security, not rebuilding.

  This suggests the gap is real, but also that the legal risk is what deters incumbents.
- Sidekick's price points ($24-$300/mo per seat, $5k/seat/yr self-hosted) are a useful benchmark for the analysis-assistant layer.

### Gaps
- I did not research AI app builders that work from screenshots or specs (v0, Lovable, Bolt, screenshot-to-code by abi). The search returned no results for screenshot-to-code.
- Binary-to-source / decompiler-LLM startups beyond RevEng.AI were not covered (for example LLM4Decompile-style research and Ghidra AI forks).
- I found no funding or pricing for Moderne, Mechanical Orchard rounds, or other COBOL migration startups in this pass.
- No Hex-Rays pricing for AI features was found.

## 5. What practitioners report works vs. fails in large LLM-agent reimplementations

### Takeaway
What works: well-specified targets with existing conformance suites or a known-good oracle, terse fast tests, parallel agents coordinated through git or tasks, and design-doc-first workflows. What fails or is overstated: regressions as the codebase grows, agents converging on the same blocker, claims of "from scratch" or "parity" that do not survive scrutiny (FastRender, ArtCraft), and weak provenance for clean-room claims.

### Cited Findings
- **Works: conformance suites as the "cheat code".** Willison on FastRender: the browser was chosen because it is well specified. JustHTML ports were completed in hours because they had 9,200 html5lib tests. — [Simon Willison](https://simonwillison.net/2026/Jan/23/fastrender/); [Simon Willison](https://simonwillison.net/2025/Dec/15/porting-justhtml/)
- **Works: oracle-based debugging.** When all agents got stuck on the same Linux kernel bug, Carlini used GCC as an oracle to bisect which files the new compiler miscompiled. — [InfoQ](https://www.infoq.com/news/2026/02/claude-built-c-compiler/)
- **Works: context-economical tests.** Carlini limited verbose output and added 1-10% sampling test modes. — [BetterStack](https://betterstack.com/community/guides/ai/anthropic-ai-agents-c-compiler/)
- **Fails: regressions and capability ceiling.** New features frequently broke existing functionality, and the project "nearly reached the limits" of Opus 4.6. Critics also said human-built scaffolding was underplayed. — [InfoQ](https://www.infoq.com/news/2026/02/claude-built-c-compiler/)
- **Fails: rigid up-front planning.** Cursor found detailed advance planning too rigid and moved to dynamic task selection. Each cycle restarts from a clean slate, and a judge agent checks completion. — [Simon Willison](https://simonwillison.net/2026/Jan/19/scaling-long-running-autonomous-coding/)
- **Fails: overclaiming.** FastRender barely compiled, CI was failing and there were no build instructions at release. — [The Register](https://theregister.com/2026/01/26/cursor_opinion); [R&D World](https://www.rdworldonline.com/?p=81571). ArtCraft claimed a target of 100% parity in a month, but only about 2 of 7 apps are usable, and its own README says menu wiring "measures wiring, not behaviour". — [Tom's Hardware](https://www.tomshardware.com/software/video-editing-graphic-design/solo-developer-rebuilds-adobe-creative-suite-in-rust-using-claude-releases-it-free-to-all-targets-100-percent-parity-in-one-month-despite-piracy-claims-and-safety-warnings); [GitHub storytold/photocraft](https://github.com/storytold/photocraft)
- **Fails: provenance and legal hygiene.** In the chardet case the agent read one original file, the maintainer had 10+ years of exposure, and the same package name was reused. All of these were used against the clean-room claim. JPlag similarity metrics were offered as mitigation. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)
- **Open legal risk.** Willison expects commercial litigation once companies see closed IP at risk. Trade-dress and patent risks were flagged for ArtCraft. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/); [LinuxCompatible](https://www.linuxcompatible.org/story/artcraft-the-free-opensource-adobe-suite-that-racked-up-43000-stars-in-days/)
- **Cost reference.** About $20k in API costs for 100k LOC of compiler over 2 weeks with 16 agents. — [InfoQ](https://www.infoq.com/news/2026/02/claude-built-c-compiler/)

### Inferences
- A platform's value is likely to sit less in code generation and more in four areas:
  - Building the oracle and conformance harness from observed behaviour.
  - Enforcing and logging information barriers between agents.
  - Producing honest behavioural-parity metrics, not counts of features or menus.
  - Producing similarity and provenance reports for legal defensibility.
- Targets without a public spec or format, such as proprietary closed file formats and complex GUI interactions, will need much heavier behaviour capture (UI traces, differential testing against the running original) than the showcase projects, which leaned on public specs.

### Gaps
- Systematic practitioner surveys and postmortems on failed large AI reimplementations are scarce. Most evidence is anecdotal or from launch posts.
- Habr and other Russian-language practitioner reports were not covered in this pass.
- I found no independent benchmark of how close ArtCraft apps are to Adobe behaviour beyond the README's own corpus metrics and press hands-on reviews.
