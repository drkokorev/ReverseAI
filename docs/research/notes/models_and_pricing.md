# Cheap LLM APIs (Chinese models) vs frontier (Claude, GPT) for agentic coding: as of 20 October 2026

Research date: 2026-10-20. Prices are USD per 1M tokens (MTok) unless stated. "Official" means the provider's own pricing or docs page, fetched on 2026-10-20. Anything taken from aggregators (morphllm.com, benchlm.ai, llm-stats.com, blogs) is labeled as such, and vendor-reported benchmark numbers are labeled "self-reported". Several aggregator pages (morphllm.com) returned HTTP 429, so some numbers come only from search-result snippets. Those are flagged and should be re-checked.

## Q1. Newest models and official API pricing (Chinese providers and frontier)

### Takeaway
Since mid-2026 the price gap has narrowed at the top and widened at the bottom. The frontier mid tier is now $2/$10 (Claude Sonnet 5/5.5, GPT-6.1 Sol), while the strongest Chinese flagship, Kimi K3, is $3/$15, which is no cheaper than Sonnet. The real cost advantage is in the Chinese "workhorse" tier: DeepSeek V4.1 Flash ($0.15–0.30 / $0.60–1.20), GLM-5.3 ($1.40/$4.40), MiniMax M3 (~$0.30–0.60 / $1.20–2.40) and Qwen3-Coder-Flash ($0.30/$1.50). These are roughly 5–30x cheaper per output token than Sonnet-class models. The frontier vendors now also ship cheap tiers that compete on price: Claude Haiku 5.5 at $0.10/$0.50 and GPT-6 Luna at $0.10/$0.50.

### Cited Findings

**Anthropic (official, fetched 2026-10-20)**: [platform.claude.com pricing](https://platform.claude.com/docs/en/about-claude/pricing)

| Model | Input | 5m cache write | 1h cache write | Cache hit | Output |
|---|---|---|---|---|---|
| Claude Fable 5.1 | $10 | $12.50 | $20 | $0.25 (0.025x) | $50 |
| Claude Mythos 5.1 (limited availability, verification program only) | $10 | $12.50 | $20 | $0.25 | $50 |
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 (0.05x) | $20 |
| Claude Opus 5 / 4.8 / 4.7 / 4.6 / 4.5 | $5 | $6.25 | $10 | $0.50 | $25 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 (0.05x) | $10 |
| Claude Sonnet 5 | $2 | $2.50 | $4 | $0.20 | $10 |
| Claude Sonnet 4.6 | $3 | $3.75 | $6 | $0.30 | $15 |
| Claude Haiku 5.5 (prompt ≤100K tokens) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| Claude Haiku 5.5 (prompt >100K tokens) | $0.50 | $0.625 | $1 | $0.05 | $2.50 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 | $5 |

- Sonnet 5 launched at an introductory $2/$10 "through August 31, 2026". Anthropic has since made $2/$10 the standard price, and the planned rise to $3/$15 on 2026-09-01 will not happen. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Claude 4.6 and later (except Haiku 5.5) include the full 1M-token context at standard pricing, with no long-context surcharge. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- The Batch API gives 50% off input and output, and it stacks with caching. US-only inference (`inference_geo: "us"`) costs 1.1x. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Claude 4.7 and later use a newer tokenizer that produces about 30% more tokens for the same text. Per-token prices therefore understate the real cost compared with older Claude models and with other vendors' tokenizers. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Opus 5.5 was released 2026-09-22. LLM Stats reports Anthropic's claim that it costs about 40% less to run than Opus 5 at default settings. [LLM Stats](https://llm-stats.com/blog/research/claude-opus-5-5-launch)
- Sonnet 5.5 was released 2026-09-28. [remio.ai on the AA Coding Agent Index](https://www.remio.ai/post/artificial-analysis-coding-agent-index-puts-claude-first-but-cost-reorders-the-l)

**OpenAI (official, fetched 2026-10-20)**: [developers.openai.com pricing](https://developers.openai.com/api/docs/pricing). "Short context" means ≤272K input tokens. The long-context rate is shown second.

| Model | Input | Cached | Output | Long-ctx in / out |
|---|---|---|---|---|
| gpt-6-astra | $10 | $1.00 | $50 | $20 / $75 |
| gpt-6.1-sol | $2 | $0.10 | $10 | $4 / $15 |
| gpt-6-sol | $2 | $0.20 | $10 | $4 / $15 |
| gpt-6-luna | $0.10 | $0.01 | $0.50 | $0.20 / $0.75 |
| gpt-5.6-sol (promo pricing at least through 2026-11-21) | $4 | $0.40 | $20 | $8 / $30 |
| gpt-5.6-terra | $2 | $0.20 | $12 | |
| gpt-5.6-luna | $0.20 | $0.02 | $1.20 | |
| gpt-5.5 | $5 | $0.50 | $30 | $10 / $45 |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 | |
| gpt-5.3-codex | $1.75 | $0.175 | $14 | |

- The Batch and Flex tiers are 50% off. The "Fast" tier (formerly Priority) is 2x. There is also an "Ultrafast" tier: 6x for gpt-6.1-sol. Regional data-residency endpoints carry a 10% uplift. [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- GPT-6.1 Sol was released around 2026-09-29. [remio.ai](https://www.remio.ai/post/artificial-analysis-coding-agent-index-puts-claude-first-but-cost-reorders-the-l)

**DeepSeek (official, fetched 2026-10-20)**: [api-docs.deepseek.com pricing](https://api-docs.deepseek.com/quick_start/pricing)

| Model | Cache hit (off-peak / peak) | Cache miss (off-peak / peak) | Output (off-peak / peak) | Context / max output | Concurrency |
|---|---|---|---|---|---|
| deepseek-flash (DeepSeek-V4.1-Flash-1017) | $0.003 / $0.006 | $0.15 / $0.30 | $0.60 / $1.20 | 1M / 384K | 2,500 |
| deepseek-v4-pro (DeepSeek-V4-Pro-0813) | $0.022 / $0.044 | $0.66 / $1.32 | $1.98 / $3.96 | 1M / 384K | 500 |

- Peak hours (2x price) are 01:00–04:00 and 06:00–10:00 UTC, Monday to Friday, excluding Chinese public holidays. Peak overlaps the EU/RU working morning. [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)
- The peak/off-peak scheme took effect 2026-08-16–17. Earlier mid-2026 prices were V4-Flash $0.14/$0.28 and V4-Pro $0.435/$0.87, now superseded. [TechTimes, 2026-08-17](https://www.techtimes.com/articles/324764/20260817/deepseek-v4-api-prices-quadruple-peak-what-developers-pay-starting-now.htm); [benchlm.ai](https://benchlm.ai/deepseek/api-pricing)
- The legacy `deepseek-v4-flash` name is retired and now routes to V4.1-Flash-1017. Search and Fetch tools cost $0.75 per 1K requests. Server-side tool calls made via Claude Code or Codex are free until per-request billing starts on 2026-11-01 (Beijing time). [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)
- V4.1-Flash-1017 was released 2026-10-17 with MIT-licensed weights. [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do)

**Moonshot Kimi (official, fetched 2026-10-20)**: [platform.kimi.ai pricing](https://platform.kimi.ai/docs/pricing/chat)

| Model | Cache hit | Input | Output | Context |
|---|---|---|---|---|
| kimi-k3 | $0.30 | $3.00 | $15.00 | 1,048,576 |
| kimi-k2.7-code | $0.19 | $0.95 | $4.00 | 262,144 |
| kimi-k2.7-code-highspeed | $0.38 | $1.90 | $8.00 | 262,144 |
| kimi-k2.6 | $0.16 | $0.95 | $4.00 | 262,144 |

- K3 cache writes are billed separately: $3.00 for a 5-minute TTL and $6.00 for a 1-hour TTL. This mirrors Anthropic's scheme. [Kimi pricing](https://platform.kimi.ai/docs/pricing/chat)
- K3 went live 2026-07-17. It is a 2.8T-parameter MoE (896 experts, 16 active), multimodal, with one flat price across the 1M context. Only max reasoning effort is available. Weights were promised for 2026-07-27, with no license stated in the source. [Trilogy AI Substack](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
- An aggregator lists third-party hosting of K3 at $2.50/$14. [morphllm.com, via search snippet; page returned 429](https://www.morphllm.com/best-ai-model-for-coding)

**Zhipu / Z.ai GLM (official, fetched 2026-10-20)**: [docs.z.ai pricing](https://docs.z.ai/guides/overview/pricing)

| Model | Input | Cached input | Output |
|---|---|---|---|
| GLM-5.3 / 5.2 / 5.1 | $1.40 | $0.26 | $4.40 |
| GLM-5.3-FlashX | $0.37 | $0.075 | $1.25 |
| GLM-5.3-Flash | $0.15 | $0.03 | $0.50 |
| GLM-5 | $1.00 | $0.20 | $3.20 |
| GLM-4.7 / 4.6 | $0.60 | $0.11 | $2.20 |
| GLM-4.7-Flash / 4.5-Flash | free | free | free |

- Cache storage is "limited-time free". The pricing page did not list context lengths or Coding Plan prices. [Z.ai pricing](https://docs.z.ai/guides/overview/pricing)
- An aggregator lists GLM-5.3 at $1.19/$6 from a third-party host. [morphllm.com, snippet](https://www.morphllm.com/best-ai-model-for-coding)

**MiniMax M3 (secondary sources only; prices conflict)**
- Implicator reports a list price of $0.60 in / $2.40 out for inputs up to 512K. Codersera and others report $0.30/$1.20, described as a "permanent 50% discount" on OpenRouter. The model has a 1M context. [Implicator](https://www.implicator.ai/minimax-promises-m3-weights-after-1m-context-model-launch/); [Codersera](https://codersera.com/blog/minimax-m3-developer-guide/amp/)
- Weights are on Hugging Face (MiniMaxAI/MiniMax-M3, with an official MXFP8 quant) under a custom MiniMax Community License, not MIT. [Codersera](https://codersera.com/blog/minimax-m3-developer-guide/amp/); [Verdent](https://www.verdent.ai/guides/how-to-use-minimax-m3)

**Alibaba Qwen (mostly secondary; check the official page)**
- The flagship Qwen3.8-Max costs $2 in / $6 out, with $0.25 cache hits on the international tier. It reportedly reached GA on 2026-08-03. [subconscious.dev](https://www.subconscious.dev/providers/alibaba-cloud); [lieke-ai.com](https://lieke-ai.com/en/articles/qwen-api-pricing-2026.html)
- Qwen3.7-Max costs $2.50/$7.50 per one source, which also mentions a 50% promo. [techjacksolutions](https://techjacksolutions.com/ai-tools/qwen/qwen-pricing/)
- qwen3-coder-flash (Singapore, international) starts at $0.30 in / $1.50 out for prompts up to 32K, with tiered pricing by context length. [Alibaba Cloud Model Studio official](https://www.alibabacloud.com/help/en/model-studio/model-pricing)
- Aggregators list Qwen3.5-Plus at $0.40/$2.40 and Qwen3.5-397B at $0.60/$3.60 (conflict: another source says $1.20/$6). [benchlm.ai](https://benchlm.ai/alibaba/api-pricing); [inferencehub](https://inferencehub.org/blog/alibaba-cloud-qwen-api-pricing-2026/)
- The free developer tier reportedly ended on 2026-04-15. [eesel.ai](https://www.eesel.ai/blog/qwen-pricing)

**Others seen in rankings:** Xiaomi MiMo-V2.5-Pro (open, Terminal-Bench 2.0 68.4%), StepFun Step-3.5-Flash and Step 3.7 Flash, and Meta Muse Spark. [llm-stats Terminal-Bench 2.0](https://llm-stats.com/benchmarks/terminal-bench-2); [aicost.org](https://aicost.org/blog/openrouter-monthly-token-usage-ranking-2026-chinese-models-dominate)

### Inferences
- **Price per output MTok, from cheapest to most expensive (list, non-batch):** DeepSeek Flash off-peak $0.60 ≈ Haiku 5.5 $0.50 ≈ GPT-6 Luna $0.50 < MiniMax M3 ~$1.20–2.40 < Qwen3-Coder-Flash $1.50 < DeepSeek V4 Pro $1.98–3.96 < GLM-5.3 $4.40 ≈ Kimi K2.7-code $4.00 < Qwen3.8-Max $6 < Sonnet 5.5 / GPT-6.1 Sol $10 < Kimi K3 $15 < Opus 5.5 $20 < Fable 5.1 / GPT-6 Astra $50.
- On a cheap tier, Chinese models no longer have a monopoly. Haiku 5.5 and GPT-6 Luna match DeepSeek Flash on list price and avoid the data-jurisdiction risk. A head-to-head agentic benchmark among these three cheap tiers was not found and should be measured in-house.
- Kimi K3 is priced above Sonnet 5.5 and GPT-6.1 Sol, so it is not a "cheap" option. Its value lies in being open-weight (if the weights did ship) and in its benchmark strength.
- DeepSeek's peak window covers 09:00–13:00 Moscow time on weekdays, so batch or off-peak scheduling matters for a Russia-based team.

### Gaps
- Official Qwen and MiniMax pricing pages were not fetched directly. The MiniMax list price conflicts between $0.30/$1.20 and $0.60/$2.40.
- No official ByteDance Seed/Doubao pricing for October 2026 was found within the search budget.
- It is not confirmed whether Kimi K3 weights were actually released on 2026-07-27, or under what license.
- Context windows for GLM-5.3 and Qwen3.8-Max were not confirmed from official pages.

## Q2. Agentic coding benchmark scores and cost per task

### Takeaway
Benchmarks are fragmented and largely saturated as of October 2026. SWE-bench Verified is above 90% for top models. Terminal-Bench has versions 2.0, 2.1 and 4.0 that get mixed up across sources, and most current numbers are self-reported. On independently aggregated leaderboards, frontier closed models still lead. On Terminal-Bench 2.0, GPT-5.5 scores 82.7%, Claude Sonnet 5 80.4% and Claude Opus 4.8 74.6%, while the best open Chinese models score around 67–70% (GLM-5.1 69.0%, DeepSeek-V4-Pro-Max 67.9%, Kimi K2.6 66.7%). The cost per task from Artificial Analysis is the most decision-relevant metric. It shows that token efficiency (GPT-6.1 Sol at about 3.2M tokens per task, versus about 27.7M for Sonnet 5.5 at max effort) can matter more than list price.

### Cited Findings

**Terminal-Bench 2.0 (llm-stats.com, last updated 2026-10-20):** [llm-stats](https://llm-stats.com/benchmarks/terminal-bench-2)
- Closed models: GPT-5.5 82.7%, Claude Mythos Preview 82.0%, Claude Sonnet 5 80.4%, GPT-5.3 Codex 77.3%, Gemini 3.5 Flash 76.2%, GPT-5.4 75.1%, Claude Opus 4.8 74.6%, Qwen3.7-Plus 70.3%, Qwen3.7-Max 69.7%.
- Open models: GLM-5.1 69.0%, MiMo-V2.5-Pro 68.4%, DeepSeek-V4-Pro-Max 67.9%, Kimi K2.6 66.7%, Qwen3.6-27B 59.3%, MiniMax M2.7 57.0%, DeepSeek-V4-Flash-Max 56.9%, GLM-5 56.2%.
- The newest models are not yet listed: Opus 5.5, Sonnet 5.5, GPT-6.x, Kimi K3, GLM-5.3, DeepSeek V4.1 Flash.

**Newer benchmark variants (all self-reported):**
- DeepSeek V4.1-Flash-1017 scores 77.0 on DeepSWE v1.1 (vs Claude Opus 5 at 74.0) and 42.3 on Terminal-Bench 4.0 (vs Opus 5 at 51.8). Its Artificial Analysis Intelligence Index is 45, and its cost per AA evaluation task is $0.26 (down from $0.49). [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do)
- Claude Opus 5.5 scores 66.4% on Terminal-Bench 4.0 at xhigh effort (self-reported, not independently verified). [LLM Stats](https://llm-stats.com/blog/research/claude-opus-5-5-launch); [benchlm.ai](https://benchlm.ai/md/models/claude-opus-5-5.md)
- Claude Opus 5 (2026-07-24): SWE-bench Verified 96%, SWE-bench Pro 79.2% (as reported by aggregators). [LLM Stats search result](https://llm-stats.com/blog/research/claude-opus-5-5-launch); [dev.to](https://dev.to/raxxostudios/claude-opus-5-benchmarks-what-the-numbers-actually-show-35gf)
- Kimi K3: AA Intelligence Index 57.1 (4th of 189), cost per AA index task $0.94 (vs $1.04 for GPT-5.6 Sol max, $2.75 for Fable 5, $0.47 for GLM-5.2), FrontierSWE 81.2 (vs Fable 5 at 86.6), DeepSWE 67.5. On Terminal-Bench it is reported "within 0.5 points of GPT-5.6 Sol". It ranks #1 on Arena Code WebDev. Moonshot itself says K3 still trails Fable 5 and GPT-5.6 Sol on overall user experience. [Trilogy AI](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
- Terminal-Bench 2.1 (Apodex 1.1 report): Gemini 3.6 Flash 91.9, Kimi K3 88.3, DeepSeek V4 Flash 0731 82.7, Claude Opus 5 77.3. SWE-bench Verified in the same report: Claude Opus 5 92.2, Kimi K3 80.8. [arXiv 2608.23283](https://arxiv.org/pdf/2608.23283)
- SWE-bench Verified per Vals AI, cited by an aggregator: GLM-5.3 95.4%, Kimi K3 93.4%. MiniMax M3 scores 80.5% (self-reported). This conflicts with the Apodex report's 80.8% for K3. [morphllm.com best-open-source, snippet](https://www.morphllm.com/best-open-source-coding-model-2026)
- SWE-bench Pro (Morph aggregate, September 2026, mostly self-reported): Claude Opus 5.5 89.9% (self-reported; conflicts with the same page's note that the best standardized public-set score as of 2026-09-14 was 61.5%), Qwen3.8-Flash-Next 62.5%, GLM-5.2 62.1%, MiniMax M3 59.0%, Kimi K2.6 58.6%. [morphllm SWE-bench Pro, snippet](https://www.morphllm.com/swe-bench-pro)

**Artificial Analysis Coding Agent Index v1.5 (harness plus model; article dated 2026-10-03):** [remio.ai](https://www.remio.ai/post/artificial-analysis-coding-agent-index-puts-claude-first-but-cost-reorders-the-l); [AA methodology](https://artificialanalysis.ai/methodology/coding-agents-benchmarking)
- Claude Code + Sonnet 5.5 (max): score 68 (DeepSWE 72%, Terminal-Bench 66%, SWE-Atlas-QnA 67%), about 27.7M tokens and about 90 minutes per task, at about 13.6x the cost of the GPT-6.1 Sol xhigh baseline.
- Antigravity + Gemini 4 Argon: 64, at about 5.6x the cost.
- Codex + GPT-6.1 Sol (xhigh): 63, about 3.2M tokens and about 15.5 minutes per task, at about $1.04 per task (the 1x baseline).
- Claude Code + Sonnet 5.5 at medium effort (the Claude Code default) scores 46. At high effort it scores 55, and at xhigh 63.
- Opencode + GLM-5.3 scores 54 at $4.24 per task. That is more expensive per task than GPT-6.1 Sol xhigh despite GLM's lower token price. [AA comparison via search snippet](https://artificialanalysis.ai/agents/coding-agents/comparisons/codex-vs-opencode)
- DeepSeek V4 Pro in Claude Code cost about $0.35 per task when the index launched (older figure; date not confirmed). [AA, via search snippet](https://x.com/ArtificialAnlys/status/2053865095076438427?lang=en)
- AA posted that GPT-6 Astra matches Fable 5 on the Coding Agent Index at lower cost. [AA on X](https://x.com/ArtificialAnlys/status/2095595489031000350)

### Inferences
- The cost per task is driven by token volume and the number of reasoning turns, not by list price alone. GLM-5.3 at $4.24 per task versus GPT-6.1 Sol at $1.04 is a direct counterexample to "cheaper per token means cheaper per task". The platform should benchmark cost per *resolved* task on its own workload.
- Effort level matters as much as model choice. Sonnet 5.5 ranges from 46 (medium) to 68 (max), and the cost rises steeply along that range.
- On independent leaderboards, Chinese open models trail the frontier by roughly 6 to 15 points on Terminal-Bench 2.0. Their self-reported numbers on newer benchmarks sometimes claim parity. Independent re-evaluation is pending for Kimi K3, GLM-5.3 and DeepSeek V4.1.

### Gaps
- No October 2026 data was found for tau-bench/tau²-bench, BFCL v4 or Aider Polyglot covering the current models. These benchmarks appear to have fallen out of use in launch reports, and none of the fetched sources reported them.
- No official tbench.ai or swebench.com leaderboard was fetched. No official SWE-bench Verified score for Opus 5.5, Sonnet 5.5 or GPT-6.1 Sol was found.
- No Artificial Analysis cost-per-task figures were found for Opus 5.5, Kimi K3 (in a coding harness) or DeepSeek V4.1 Flash in a coding harness.

## Q3. Anthropic/OpenAI-compatible endpoints and routers

### Takeaway
Most major Chinese providers now expose Anthropic Messages-compatible endpoints. These can be plugged into Claude Code or the Claude Agent SDK through `ANTHROPIC_BASE_URL` plus `ANTHROPIC_AUTH_TOKEN`. That makes a "Claude Agent SDK harness with a swappable model" architecture feasible. OpenRouter is the dominant router, and Chinese models carry a large share of its traffic. Reliability and rate limits on new flagship models (for example Kimi K3 on OpenRouter) remain a problem.

### Cited Findings
- DeepSeek offers an official Anthropic-format endpoint at `https://api.deepseek.com/anthropic` for both models. [DeepSeek pricing/docs](https://api-docs.deepseek.com/quick_start/pricing)
- Z.ai GLM's Anthropic endpoint is `https://api.z.ai/api/anthropic`. Do not use the OpenAI-style `/api/coding/paas/v4` path with Claude Code. [datallmlab guide](https://www.datallmlab.com/blog/claude-code-with-glm-5.html); [mcsaguru](https://mcsaguru.com/anthropic-compatible-endpoints-claude-code)
- Alibaba provides a Claude Code proxy at `https://dashscope-intl.aliyuncs.com/api/v2/apps/claude-code-proxy` and a separate Coding Plan endpoint (third-party guide). [mcsaguru](https://mcsaguru.com/anthropic-compatible-endpoints-claude-code)
- MiniMax M3's API page lists both Anthropic-compatible and OpenAI-compatible endpoints. [Implicator](https://www.implicator.ai/minimax-promises-m3-weights-after-1m-context-model-launch/); [Verdent](https://www.verdent.ai/guides/how-to-use-minimax-m3)
- Moonshot appears in lists of Anthropic-compatible base URLs (`api.moonshot.ai/anth…`, truncated, unconfirmed). The K3 launch write-up documents only an OpenAI-compatible API (`kimi-k3`), OpenRouter (`moonshotai/kimi-k3`) and Kimi Code. [mcsaguru](https://mcsaguru.com/anthropic-compatible-endpoints-claude-code); [Trilogy AI](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
- OpenRouter and LLM gateways (for example LLMGateway) expose Anthropic-format endpoints usable with the same environment variables. A cached claude.ai login can override environment-variable settings in Claude Code. [andrewbaker.ninja, 2026-08-10](https://andrewbaker.ninja/2026/08/10/how-to-run-claude-code-on-openrouter-with-alternative-models-like-deepseek-the-anthropic_base_url-guide/); [LLMGateway docs](https://docs.llmgateway.io/features/anthropic-endpoint)
- Self-hosting servers (BentoML, Modular MAX) also offer Anthropic-compatible APIs for open weights. [BentoML](https://bentoml.com/llm/model-interaction/anthropic-compatible-api); [Modular](https://handbook.modular.com/model-interaction/anthropic-compatible-api/)
- **OpenRouter share (secondary blogs, figures conflict):** as of June 2026, China-origin models accounted for about 61% of volume, or about 46% when counting only explicitly tagged Chinese vendors. DeepSeek is the single largest provider at 17.6%, with Anthropic at 14.8%; another report puts Claude at 13.3%. In August 2026, Chinese models held 8 of the weekly top-10 spots, including GLM 5.2, MiniMax M3 and Step 3.7 Flash. [nodemini](https://nodemini.com/en/blog/2026-openrouter-rankings-june-chinese-models-61-percent.html); [tech-insider](https://tech-insider.org/au/chinese-ai-models-openrouter-2026/); [KuCoin news](https://www.kucoin.com/news/flash/chinese-models-dominate-openrouter-weekly-token-usage-ranking)
- **Reliability:** while collecting 20 completions from Kimi K3 via OpenRouter at launch, the tester got 311 HTTP 429 responses. K3 also requires the harness to return the full assistant message, including reasoning and tool-call fields, on every turn, because it is sensitive to missing thinking history. In four test requests it exhausted a 4,096-token output limit on reasoning alone. [Trilogy AI](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
- DeepSeek concurrency limits are 2,500 for Flash and 500 for V4 Pro. [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)

### Inferences
- Compatibility at the API-format level does not guarantee feature parity. Claude-specific features (cache_control semantics, extended-thinking blocks, server tools, effort parameters) may be ignored or behave differently. Run an integration test per provider.
- For a multi-agent platform, a gateway layer (OpenRouter, LiteLLM, or an in-house gateway) that normalizes Anthropic and OpenAI formats and handles fallback on 429/5xx errors is advisable. Rate-limit behavior at launch of new Chinese flagships is poor.

### Gaps
- No October 2026 pricing or uptime data was gathered for Together, Fireworks, SiliconFlow or DeepInfra. OpenRouter uptime statistics per provider were not fetched.
- The official Moonshot Anthropic-endpoint path is not confirmed.

## Q4. Open-weight licenses and self-hosting

### Takeaway
DeepSeek (MIT) and GLM (historically MIT) are the most permissive for commercial use and fine-tuning. MiniMax M3 ships under a custom community license with conditions. The Kimi K3 license and release status are unconfirmed. Frontier-scale Chinese MoE models need multi-node GPU clusters to self-host, so self-hosting only makes sense for data-sovereignty reasons or at very high volume.

### Cited Findings
- DeepSeek V4.1-Flash-1017 weights are MIT-licensed and can be downloaded, run and adapted commercially. [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do)
- GLM-5.2 is described as an "open-weight MIT model". [morphllm GLM-5.2 vs Kimi K3, snippet](https://www.morphllm.com/glm-5-2-vs-kimi-k3)
- MiniMax M3 uses the MiniMax Community License, which is open-weight but not permissive. Read it before shipping. [Verdent](https://www.verdent.ai/guides/how-to-use-minimax-m3); [Codersera](https://codersera.com/blog/minimax-m3-developer-guide/amp/)
- Kimi K3 is a 2.8T-parameter MoE. The recommended deployment spans at least 64 accelerators, and the weights were promised for 2026-07-27. [Trilogy AI](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
- Several Qwen models (for example Qwen3.6-27B and Qwen3.6-35B-A3B) are open. The top Qwen models (3.7-Max, 3.8-Max) appear to be closed. [llm-stats](https://llm-stats.com/benchmarks/terminal-bench-2)
- Self-hosting the open weights is the main mitigation for offshore-data-transfer concerns. [layer3labs](https://www.layer3labs.io/guides/chinese-ai-models-security-risks); [layer3labs comparison](https://www.layer3labs.io/comparisons/best-chinese-ai-models)

### Inferences
- A small open coding model (for example Qwen3.6-27B, which scores 59.3% on Terminal-Bench 2.0) can run on a single node. That makes it a realistic on-prem option for code that must not leave the perimeter. Larger MoE models (Kimi K3, DeepSeek V4 Pro) need cluster-scale hardware.

### Gaps
- No concrete October 2026 self-hosting cost figures ($/hour per GPU node, or throughput per GPU) were found for DeepSeek V4 or GLM-5.3. The Spheron article on self-hosting compared with Opus 5 was not fetched. [Spheron](https://www.spheron.network/blog/claude-opus-5-api-vs-self-hosted-llms-cost-privacy-2026/)
- The exact license texts were not verified for GLM-5.3, Kimi K3 or Qwen3.8.

## Q5. Prompt caching support and pricing

### Takeaway
Every major provider now discounts cached input heavily. For agentic loops that resend long contexts, the cached-input price often matters more than the base price. The cheapest cache reads are DeepSeek Flash ($0.003–0.006), Claude Haiku 5.5 ($0.01), GPT-6 Luna ($0.01) and GPT-6.1 Sol ($0.10). Anthropic's newest models cut the cache-read multiplier from 0.1x to 0.05x (Opus 5.5 and Sonnet 5.5) and 0.025x (Fable 5.1).

### Cited Findings
- **Anthropic:** cache writes cost 1.25x base (5-minute TTL) or 2x base (1-hour TTL). Cache reads cost 0.1x base, 0.05x for Opus 5.5 and Sonnet 5.5, and 0.025x for Fable 5.1 and Mythos 5.1. Caching stacks with the Batch discount. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- **OpenAI:** cached input is typically 0.1x base, and 0.05x for gpt-6.1-sol ($0.10 against $2). No separate write charge is listed. [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- **DeepSeek:** cache hits cost about 2% of the cache-miss price (Flash: $0.003 vs $0.15 off-peak; Pro: $0.022 vs $0.66). [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)
- **Kimi K3:** cache hits cost $0.30 (0.1x). Cache writes are billed at $3 (5-minute) or $6 (1-hour). [Kimi pricing](https://platform.kimi.ai/docs/pricing/chat)
- **GLM:** cached input costs about 0.19x ($0.26 vs $1.40), and storage is currently free. [Z.ai pricing](https://docs.z.ai/guides/overview/pricing)
- **Qwen3.8-Max:** cache hits cost $0.25 (0.125x). [subconscious.dev](https://www.subconscious.dev/providers/alibaba-cloud)

### Inferences
- In a multi-agent platform with a large shared system prompt and repository context, cache-hit rates of 80–90% are realistic, so the effective input cost is dominated by cache reads. Under that assumption, DeepSeek Flash input becomes effectively near-free, and Claude Sonnet 5.5 cache reads ($0.10) are cheaper than GLM-5.3's ($0.26).

### Gaps
- MiniMax M3 caching prices were not found.

## Q6. Risks: privacy, retention, training use, sanctions, rate limits, uptime

### Takeaway
For customer code, the hosted Chinese APIs carry material legal and reputational risk. Data is stored in the PRC. Training-use and retention terms are unclear: DeepSeek publishes no zero-data-retention tier and no fixed retention window. The US has banned DeepSeek from federal civilian agencies and from defense contract work. Zhipu has been on the US Entity List since January 2025. In September 2026 China opened a data-security probe into DeepSeek and Moonshot. Commercial private-sector use is not banned in the US. The usual mitigations are to self-host the open weights, or to use them through Western hosts (OpenRouter providers, Together, Fireworks), keeping the China-hosted API for non-sensitive workloads only.

### Cited Findings
- **US federal ban on DeepSeek:** a DHS order signed 2026-07-24 under the Federal Acquisition Supply Chain Security Act was disclosed around 2026-10-19. It covers federal civilian agencies and third-party implementations of DeepSeek technology. Separately, Section 1532 of the FY2026 NDAA bars the Pentagon and defense contractors from using DeepSeek AI for defense work. [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do); [CNBC 2026-10-20](https://cnbc.com/2026/10/20/us-deepseek-federal-agency-ban.html)
- Commercial use is not barred by federal rule. However, sending export-controlled technical data to DeepSeek's China-hosted services may require an export license. [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do)
- **Zhipu (Z.ai)** has been on the US Entity List since January 2025. Sending export-controlled technical data to its hosted API requires a license, which faces a presumption of denial. [search summary citing vibraniumlabs](https://vibraniumlabs.ai/blog/chinese-ai-models-sanctioned-whats-actually-happening)
- **China's probe:** Chinese authorities reportedly opened a data-security probe into DeepSeek and Moonshot after Anthropic accused them of routing sensitive data through Claude models. This rests on a single-outlet report (The Information, relayed by Bloomberg, 2026-09-22) and is not otherwise confirmed. [Bloomberg](https://www.bloomberg.com/news/articles/2026-09-22/china-probes-deepseek-moonshot-over-data-security-information)
- **DeepSeek data terms:** API data is collected, processed and stored in the PRC. Sources conflict on whether API inputs are used for training: one says training is on by default with no clear API opt-out (as of April 2026), another says the API terms grant no training right. No fixed API retention window and no zero-data-retention tier are published. [meetily.ai](https://meetily.ai/llm-privacy/deepseek); [sagnikbhattacharya](https://sagnikbhattacharya.com/blog/is-deepseek-safe-business-data); [DeepSeek Open Platform ToS](https://platform.deepseek.com/downloads/DeepSeek%20Open%20Platform%20Terms%20of%20Service.html); [guptadeepak](https://guptadeepak.com/ai-models/deepseek/deepseek-v4-1-flash/)
- A commercial blog states that none of the Chinese vendors offer a BAA, SOC 2 or HIPAA coverage on their hosted APIs (unverified). [layer3labs](https://www.layer3labs.io/comparisons/best-chinese-ai-models)
- **VentureBeat's enterprise checklist:** inventory every Chinese model in use, including fine-tunes and subcontractors; keep them out of government and defense work; design for portability so that switching models is a configuration change; and monitor SAM.gov orders. [VentureBeat](https://venturebeat.com/security/deepseek-v4-1-flash-1017-arrives-with-improved-benchmarks-just-as-the-u-s-government-bans-it-from-agencies-what-enterprises-should-do)
- **Operational risks:**
  - Kimi K3 returned 311 HTTP 429 responses for 20 completions at launch and is sensitive to harness formatting. [Trilogy AI](https://trilogyai.substack.com/p/kimi-k3-is-live-pricing-benchmarks)
  - DeepSeek's peak pricing doubles cost during the EU/RU morning. [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing)
  - Pricing churn is frequent: DeepSeek prices roughly quadrupled at peak in August 2026, and Sonnet 5's price plan changed. [TechTimes](https://www.techtimes.com/articles/324764/20260817/deepseek-v4-api-prices-quadruple-peak-what-developers-pay-starting-now.htm)
- **Frontier side:** Anthropic and OpenAI offer data-residency endpoints for a 10% premium. [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing); [OpenAI](https://developers.openai.com/api/docs/pricing)

### Inferences
- For a reverse-engineering and code-analysis platform that handles customer code, the China-hosted APIs should not be the default for customer data unless contracts permit it. Running Chinese open weights on self-hosted or Western infrastructure removes the data-jurisdiction risk but not the model-provenance concerns some customers have (for example US government-adjacent customers).
- Reverse-engineering content may also trigger provider usage policies (Anthropic's Cyber Verification Program gates Mythos-class models). This is worth checking separately.

### Gaps
- Official retention and training terms for Moonshot, Zhipu, MiniMax and Alibaba international APIs were not retrieved.
- No published uptime or SLA statistics per provider were found.
- No Russia-specific sanctions analysis was done. Access from Russia to Anthropic and OpenAI and to Chinese APIs (payment, KYC, geo-blocking) was out of the searched scope and should be researched separately.

## Q7. Routing strategies and reported savings

### Takeaway
The prevailing pattern is a frontier model for planning and review with a cheap model for bulk execution. Reported savings range from 30–40% (conservative) to 64% (LangChain, median cost per task, October 2026) and about 4x on the execution side, with anecdotal claims up to 80–90%. All figures are vendor or blog reports, not controlled studies. The key caveat is that rework caused by wrong routing can erase the savings, so measure cost per shipped change rather than cost per call.

### Cited Findings
- LangChain (October 2026) reports that model routing inside the agent harness cut median cost per coding task by 64% with no noticeable quality change. [LangChain blog](https://www.langchain.com/blog/how-to-build-a-model-router-in-the-harness)
- Unblocked (June 2026) says routing typically cuts bills 30–40%, and warns that cheap mis-routes trigger rework. [getunblocked](https://getunblocked.com/blog/model-routing-coding-agents/index.md)
- Arize describes an internal workflow that dropped from about $100 to about $15–20 per run by splitting planning, exploration, implementation and review across models. This is anecdotal. [Arize](https://arize.com/blog/how-cheap-models-changed-multi-agent-economics/)
- Morph reports a 4x cost reduction from planner and executor pairs across 40 app builds. Its figures are internally inconsistent in places. [morphllm](https://www.morphllm.com/multi-agent-model-routing)
- Pioneer.ai describes "frontier planner, cheap executor" as the standard 2026 pattern but gives no numbers. [Pioneer](https://pioneer.ai/blog/how-to-choose-the-best-coding-models-in-2026)
- The Artificial Analysis Coding Agent Index shows harness and effort level changing cost by more than 10x at similar scores: Sonnet 5.5 max reaches 68 at 13.6x cost, while GPT-6.1 Sol xhigh reaches 63 at 1x. [remio.ai](https://www.remio.ai/post/artificial-analysis-coding-agent-index-puts-claude-first-but-cost-reorders-the-l)

### Inferences (suggested starting configuration for the platform; to be validated on in-house evals)
- **Planner and reviewer (low volume, high leverage):** Claude Opus 5.5 ($4/$20, cache read $0.20), or GPT-6.1 Sol xhigh ($2/$10, the most token-efficient option per AA).
- **Default executor (bulk code generation and analysis inside the Claude Agent SDK):** Claude Sonnet 5.5 at high effort ($2/$10, cache read $0.10). It needs no format adapter and has a 1M context at a flat price.
- **Cheap bulk tier (summarization, file triage, grep-like analysis, test generation):** Claude Haiku 5.5 ($0.10/$0.50) or GPT-6 Luna ($0.10/$0.50) for customer code. Use DeepSeek V4.1 Flash ($0.15–0.30 / $0.60–1.20, MIT) only for non-sensitive data, or self-hosted or through a Western host.
- **Open-weight fallback, or the on-prem option for sensitive customers:** DeepSeek V4 Pro or V4.1 Flash (MIT), GLM-5.x (MIT), or Qwen3.6-27B for a single-node deployment.
- **Avoid as the default:** Kimi K3. It costs more than Sonnet 5.5 ($3/$15), had launch-time rate limiting, and is sensitive to harness formatting.
- Cap the effort level per agent role. Effort is the largest single cost lever according to the AA data.

### Gaps
- No controlled study was found comparing "Opus plans, Sonnet or Chinese model executes" with measured savings on SWE-style tasks as of October 2026.
