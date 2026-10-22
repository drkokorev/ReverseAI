# Academic Research: LLMs for Program Comprehension, Decompilation, Specification Extraction and Large-Scale Code Generation/Translation (as of Oct 2026)

Scope note: These notes cover peer-reviewed and arXiv work from 2024 to Oct 2026. All numbers come from the primary papers unless marked otherwise. Different papers use different splits, compilers, decompiler front-ends (Ghidra vs IDA/Hex-Rays) and stripping settings, so cross-paper numbers are **not directly comparable**. Where a number is only from a secondary aggregator, it is flagged.

---

## 1. Neural decompilation and binary understanding (LLM4Decompile, Idioms, ReF Decompile, CodeInverter, RL-based decompilation, name/type recovery; frontier vs open-weight)

### Takeaway
Specialized 6.7B–22B fine-tuned decompilers now reach about 60–75% re-executability on HumanEval-Decompile (avg O0–O3), beating general frontier models used zero-shot (GPT-4o about 29%, GPT-5-mini about 57%, DeepSeek-V3 about 51% end-to-end). The best results come from three things together: (a) refining Ghidra/IDA pseudocode rather than raw assembly, (b) RL with compile/execute rewards, and (c) sampling plus reranking or test feedback at inference. Decaf reaches 83.9% functional correctness on ExeBench real -O2 with N=32 plus a learned reranker. Accuracy drops sharply with optimization level (O0 → O3) and on real-world code with user-defined types. Name and type recovery is still only about 50–65% accurate.

### Cited Findings

**LLM4Decompile family (Tan et al.; arXiv 2403.05286; HF models; GitHub albertan017/LLM4Decompile)**
- Model variants and re-executability on HumanEval-Decompile, from the repo's model table: llm4decompile-1.3b-v1.5 = 27.3%, 6.7b-v1.5 = 45.4% (end-to-end from assembly); V2 "Ref" models, which refine Ghidra pseudocode: 1.3b-v2 = 46.0%, 6.7b-v2 = 52.7%, 9b-v2 (from Yi-Coder-9B) = 64.9%, 22b-v2 = 63.6% — [LLM4Decompile GitHub](https://github.com/albertan017/LLM4Decompile)
- Training data: V1.5 used 15B tokens with max length 4,096. V2 (Ref) used 2B tokens. A 100k-sample Ghidra fine-tune script runs in about 3.5 h on one A100-40GB (under $20) and reaches 0.26 re-executability — [LLM4Decompile GitHub](https://github.com/albertan017/LLM4Decompile)
- HumanEval-Decompile has 164 C functions × 4 optimization levels (O0–O3). ExeBench eval has 2,621 real-project functions with user-defined functions, structs and macros — [LLM4Decompile GitHub](https://github.com/albertan017/LLM4Decompile)
- V1.5 end-to-end per the paper's Table 1: 6.7B avg 45.37, 33B avg 31.54. The larger model was worse in this table — [LLM4Decompile arXiv 2403.05286](https://arxiv.org/pdf/2403.05286) (via search snippet)
- **Decompile-Bench** (NeurIPS 2025 Datasets & Benchmarks): about 2M function-level binary–source pairs, filtered from about 100M collected pairs drawn from permissively licensed GitHub projects (450 GB of binaries). Decompile-Bench-Eval uses HumanEval, MBPP and GitHub repos published after 2025 to limit leakage. Fine-tuning on it gives about 20% re-executability improvement — [Decompile-Bench arXiv 2505.12668](https://arxiv.org/html/2505.12668v2); [NeurIPS 2025 proceedings](https://papers.neurips.cc/paper_files/paper/2025/hash/079cf13ae174c31f148207d94d213bdc-Abstract-Datasets_and_Benchmarks_Track.html)

**Idioms (Dramko, Le Goues, Schwartz — CMU; arXiv 2502.04536, v2 Jun 2025)**
- Joint prediction of code plus full user-defined type (UDT) definitions, using call-graph neighbor functions as context. New "realtype" dataset: 154,301 train and 2,862 eval functions. Fine-tuned bases: CodeQwen2.5-0.5B, LLM4Decompile-1.3B, CodeGemma-2B/7B (QLoRA), CodeLlama-7B — [Idioms arXiv v2](https://arxiv.org/html/2502.04536v2)
- ExeBench functional correctness: Idioms 54.4% vs LLM4Decompile 46.3% vs Nova 37.5%. Realtype O0 dependency-equivalence: 34.1% vs 27.9% vs 24.8%. Best UDT structural accuracy is only 15.1% (CodeGemma-7B). The paper reports no training compute; context windows were 2,048 and 4,096 tokens — [Idioms arXiv v2](https://arxiv.org/html/2502.04536v2)

**ReF Decompile (arXiv 2502.12221, Feb 2025)**
- Adds a relabeling strategy and function-call enhancement to end-to-end decompilation. Best config: 61.43% avg re-executability on HumanEval-Decompile — [ReF Decompile arXiv](https://arxiv.org/html/2502.12221v1). AutoDecompiler later reports Ref-Decompile 6.7B at 57.27% under its own setup — [AutoDecompiler arXiv 2606.16162](https://arxiv.org/html/2606.16162v1)

**CodeInverter Suite (Zhongguancun Lab / Tsinghua; arXiv 2503.07215, Mar/May 2025)**
- Prompting workflow that adds control-flow graphs and explicit data-mapping tables. Training set of 8.69M samples. 1.3B and 6.7B models. Reports +9.16% re-executability and +15.26% re-compilability on average across two benchmarks — [CodeInverter arXiv](https://arxiv.org/html/2503.07215v2)
- In AutoDecompiler's comparison, "CIM 6.7B" (CodeInverter model) reaches 62.05% HumanEval and 46.14% ExeBench re-executability end-to-end — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)

**SK²Decompile (Tan et al.; arXiv 2509.22114, Sep 2025; ICLR 2026)**
- Two phases. First, a "skeleton" step: binary → IR with identifiers replaced by placeholders, trained with RL using a compiler-check reward. Second, a "skin" step: an identifier-naming model with an RL reward equal to the embedding cosine similarity to reference names (qwen-embedding-0.6B). Both are initialized from LLM4Decompile-6.7B. SFT ran for 1 epoch (LLaMA-Factory). GRPO in veRL ran on a 50k-sample subset. Hardware was H800-80GB clusters — [SK2Decompile arXiv PDF](https://arxiv.org/pdf/2509.22114)
- Training data: ExeBench plus Decompile-Bench C programs compiled with GCC and Clang at O0–O3, stripped, and lifted to IDA Pro pseudocode. MinHash-LSH dedup. About 5M samples (about 2B pseudocode tokens, 1.5B IR tokens, 1.5B source tokens) — [SK2Decompile](https://arxiv.org/pdf/2509.22114)
- Re-executability on HumanEval, O0/O1/O2/O3/avg — [SK2Decompile Table 1](https://arxiv.org/pdf/2509.22114):

  | Model | O0 | O1 | O2 | O3 | Avg |
  |---|---|---|---|---|---|
  | SK²Decompile | 86.59 | 70.59 | 61.31 | 57.52 | 69.00 |
  | GPT-5-mini | 67.07 | 60.78 | 49.63 | 49.56 | 56.75 |
  | LLM4Decompile (Ref) | 67.07 | 37.25 | 33.58 | 28.32 | 41.71 |
  | Idioms | 70.73 | 25.49 | 12.41 | 10.62 | 29.81 |

  MBPP averages: SK²Decompile 59.63, GPT-5-mini 47.23, LLM4Decompile 43.05, Idioms 24.01.
- Readability: the paper reports +29.4% average R2I over Idioms on GitHub2025. It does not compare against Nova, Ref-Decompile or D-LiFT, citing unreleased models or preprocessing details — [SK2Decompile](https://arxiv.org/pdf/2509.22114)

**AutoDecompiler (Liu et al., Zhongguancun Lab / Tsinghua; arXiv 2606.16162, 15 Jun 2026) — RL multi-turn refinement**
- Base models: DeepSeek-Coder 1.3B/6.7B and Qwen3-Coder 30B. SFT on about 300K functions from the CID corpus. RL on 10K disjoint functions (O0–O3). GRPO extended to up to 3 refinement turns, with progress-aware trajectory rewards — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
- Reward is a weighted sum: C-like validity (0.5), compile-and-execute (1.0; -1 recompile fail, -0.6 runtime error, -0.3 partial I/O mismatch, +1 all tests pass), AST-subtree match (0.3), and data-flow match (0.2). Hardware: 8×H100-80GB clusters. No GPU-hours reported — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
- End-to-end from assembly, avg re-executability on HumanEval / ExeBench: AutoDecompiler-E2E 6.7B 63.11 / 40.94; CIM 6.7B 62.05 / 46.14; **DeepSeek-V3 51.22 / 39.85; GPT-4o 29.27 / 28.82**; LLM4Decompile-End 6.7B 30.94 / 17.98; IDA Pro 20.73 / 47.01; **Ghidra 14.48 / 61.51**. Classic decompilers win on real-world ExeBench — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
- Pseudocode-input, HumanEval avg re-executability: DecLLM with DeepSeek-V3 671B (reproduced) 80.49; AutoDecompiler-Pscode 30B 75.30; 6.7B 70.58; SK²Decompile 6.7B 69.00; Ref-Decompile 6.7B 57.27; LLM4Decompile-Ref 6.7B 41.71; Idioms 6.7B 29.81; **DecLLM with Qwen3-Coder 30B only 17.68**. Multi-turn RL raised re-executability from 65.09% (no RL) to 68.75% (1-turn RL) and 70.58% (3-turn RL) — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
- Inference: AutoDecompiler-E2E 6.7B took 1,903 s on HumanEval, vs 5,484 s for DecLLM on the DeepSeek-V3 API — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)

**Decaf (Shypula, Bastani, Schwartz — UPenn/CMU; arXiv 2605.11501, May 2026) — sampling plus compiler-feedback reranking**
- Generator fine-tuned from LLM4Decompile-Ref-22B-v2 (about 3 days, 2 epochs, 8×B200, max seq 5,120). Two rerankers fine-tuned from Qwen3-32B (about 2 weeks each on 8×B200). Fine-tuning set: 1.34M unstripped samples; reranker set: 1.52M — [Decaf arXiv PDF](https://arxiv.org/pdf/2605.11501)
- Sampling 32 candidates gives an 88% chance that at least one is functionally correct, vs 60% for a single sample — [Decaf](https://arxiv.org/pdf/2605.11501)
- ExeBench stripped REAL -O2, N=1: Decaf-22B 59.1% accuracy vs Idioms-Gemma-7B 26.0%, LLM4Decompile-Ref-22B 24.0%, Ghidra 34.2%. With N=32 and the learned reranker: **83.9% functional correctness and 70.9% byte-exact recompilation match**. Byte-distance reranking alone gives 81.1%. Stripped REAL -O0 with reranker: 87.3% — [Decaf Tables 3–4](https://arxiv.org/pdf/2605.11501)
- "Ghidra + custom exporter" alone reaches 80.3% accuracy on stripped real -O2. Engineering the classic decompiler's output to be recompilable is a very strong baseline — [Decaf Table 3](https://arxiv.org/pdf/2605.11501)

**Other decompilation and recompilation work**
- **DecLLM** (ISSTA 2025; HKUST + Tencent Keen Lab): iterative prompting-only repair loop using static recompilation plus runtime feedback. About 70% recompilation success upper bound with GPT-3.5/GPT-4. Recompiled code is usable for CodeQL analysis — [ISSTA 2025 listing](https://conf.researchr.org/details/issta-2025/issta-2025-papers/80/DecLLM-LLM-Augmented-Recompilable-Decompilation-for-Enabling-Programmatic-Use-of-Dec)
- **D-LiFT** (arXiv 2506.10125): RL fine-tuning with a "D-Score" that rewards readability only when accuracy passes. 55.3% more improved functions than baseline LLMs. Improves 68.2% of Ghidra-produced functions on coreutils and util-linux. Only 8.02% improvement on functions Ghidra had decompiled inaccurately, vs 86.2% on accurate ones — [D-LiFT arXiv](https://arxiv.org/html/2506.10125v2)
- **PCodeTrans** (arXiv 2603.14855, Mar 2026): hot-swaps the recompiled function into the original binary and uses differential tracing to feed runtime discrepancies back to an LLM. On raw Hex-Rays output it reports 100% function-level compilability (unstripped coreutils and binutils), 99.55% / 99.89% test-validated behavioral consistency, and over 96% on fully stripped binaries — [PCodeTrans arXiv](https://arxiv.org/abs/2603.14855?context=cs) (abstract-level; not independently reproduced per [SOTAVerified](https://sotaverified.org/papers/260314855))
- **DecompileBench** (Gao et al., ACL 2025 Findings; arXiv 2505.11340): 23,400 functions from 130 real-world programs, with runtime-aware validation plus LLM-as-judge. LLM-based methods beat commercial decompilers on understandability but have **52.2% lower functionality correctness** — [DecompileBench arXiv](https://arxiv.org/abs/2505.11340)

**Name and type recovery**
- **VarBERT** (IEEE S&P 2024): masked-LM transfer learning. Up to 84.15% of names identical to the originals on a dataset of 164,632 binaries — [search summary of VarBERT/GenNm papers](https://arxiv.org/pdf/2306.02546)
- **ReSym** (Xie et al., Purdue; ACM CCS 2024): two fine-tuned LLMs (locals and structs) plus Prolog-based aggregation and cross-checking to suppress hallucination. Dataset of 7,416 projects and 113,696 binaries. Overall accuracy 56.4% for variable names and 64.6% for types; 72.9% precision on full struct layout; F1 85.9% for detecting fragmented inlined structs/arrays; +1.5–16.5% over SOTA (DIRTY, OSPREY) — [ReSym CCS'24 PDF](https://www.cs.purdue.edu/homes/lintan/publications/resym-ccs24.pdf)
- **GenNm** (Xu et al., Purdue; NDSS 2025): generative naming from CodeGemma-2B and CodeLlama-7B/34B, using caller/callee names as context and aligning outputs to developer symbol preferences. +5.6–11.4 pp precision over SOTA. On names unseen in training, 17.3% → 22.8% — [GenNm NDSS'25 PDF](https://ndss-symposium.org/wp-content/uploads/2025-276-paper.pdf)
- **ReCopilot** (QI-ANXIN; arXiv 2505.16366, May 2025): Qwen2.5-Coder-7B with continued pretraining (36B tokens: 21B binary-domain, 10B code, 5B NL), SFT (1.7B tokens, CoT data generated with DeepSeek-V3), and DPO (2.4K pairs). 32K context. About 7.1K A800 GPU-hours total. The paper also mentions a 60B-token pretrain mixture in another section, an internal inconsistency — [ReCopilot arXiv](https://arxiv.org/pdf/2505.16366)
- ReCopilot Table 5, columns func-name / var-name / var-type / struct / decompilation / summary:

  | Model | Func name | Var name | Var type | Struct | Dec | Sum |
  |---|---|---|---|---|---|---|
  | ReCopilot-7B-DPO | 50.59 | 43.50 | 39.81 | 27.67 | 29.23 | 65.21 |
  | DeepSeek-R1 | 43.63 | 25.36 | 38.92 | 22.12 | 29.77 | 66.32 |
  | DeepSeek-V3 | 40.20 | 18.21 | 34.75 | 14.47 | 25.20 | 56.90 |
  | Qwen2.5-Coder-7B-Instruct | 34.57 | 24.07 | 30.27 | 9.09 | 23.13 | 50.49 |

  Removing the CPT stage drops the scores (e.g., var-name 43.50 → 32.98). ReCopilot's own JSON output succeeded only 92% of the time — [ReCopilot](https://arxiv.org/pdf/2505.16366)
- **Memorization caveat** (Asjad; arXiv 2609.17236, Sep 2026): on functions written after a pre-registered analysis plan (so unseen by any model), LLM refinement of decompiled code recovers names above a permutation null (+0.072 to +0.137). Destroying input dataflow, removing type prefixes or permuting names did **not** change the naming gain (dataflow effect +0.001, 95% CI [-0.026, +0.026]). Gains may come from model priors rather than from the decompiler evidence — [arXiv 2609.17236](https://arxiv.org/abs/2609.17236)

**Agentic binary RE with frontier vs open models**
- **CrackMeBench** (David & Gervais, UCL; arXiv 2605.10597, May 2026): 20 tasks (12 generated, 8 public), a no-network Docker sandbox with Ghidra, radare2, angr, gdb and Z3, a 5-minute budget and 3 submissions. Pass@3 on the 12 generated tasks: **GPT-5.5 (xhigh) 11/12, Claude Opus 4.7 7/12, Kimi K2 5/12**. On the 8 public CrackMes: 3/8, 2/8 and 1/8. Failure modes: kept exploring after finding the validation site, overfit keygens to the visible example, over-trusted decompiler output — [CrackMeBench](https://arxiv.org/html/2605.10597v1)
- **AgentRE-Bench** V3 (Windows, Aug 2026): the best of six frontier models scored 1.3618/2.0 with a budget of 25 tool calls. Stripping reduced the mean score by only 0.0416 — [AgentRE-Bench GitHub](https://github.com/agentrebench/AgentRE-Bench) (via search snippet; model names not confirmed)

### Inferences
- For a reimplementation platform, the strongest pipeline is: classic decompiler (Ghidra or IDA) → LLM refinement → recompile → differential execution against the original → sample N and rerank. Decaf, PCodeTrans and DecLLM-style feedback each add tens of points over single-shot LLM output. Raw end-to-end "assembly → C" is clearly weaker.
- Frontier general models are competitive when used agentically with tools and feedback (DecLLM with DeepSeek-V3 reaches 80.49%). Zero-shot they lag specialized 7B models. Among open-weight models, DeepSeek-V3/R1 is consistently strong. Qwen3-Coder-30B does poorly as a DecLLM backbone (17.68%) but well as an RL fine-tuning base (75.30%). Kimi K2 trails GPT-5.5 and Claude Opus 4.7 in agentic RE. I found no decompilation-specific numbers for GLM.
- O2/O3 and real-world UDT-heavy code remain the hard frontier: Idioms UDT accuracy is 15% and LLM4Decompile drops from 67% at O0 to 28% at O3.

### Gaps
- No single leaderboard compares Claude 4.x, GPT-5.x, Gemini 3, DeepSeek-V3.2, Qwen3-Coder, Kimi K2 and GLM-4.6/5 on HumanEval-Decompile under one protocol. Numbers are scattered across papers with different setups.
- Formal venues for LLM4Decompile (believed EMNLP 2024), ReF Decompile and Nova were not confirmed in this session.
- The DecompileBench paper's per-model numbers (which LLMs) were not retrieved.
- Training compute is rarely reported. Known figures: ReCopilot about 7.1K A800 GPU-hours; Decaf about 3 days on 8×B200 for the generator plus about 2 weeks per reranker; LLM4Decompile small fine-tune under $20.
- Non-C languages (C++ with templates, Rust, Go, Swift, .NET/Java bytecode) and obfuscated binaries are barely covered in the benchmarks found.

---

## 2. Specification extraction / requirements recovery; test generation from observed behavior; differential testing

### Takeaway
LLM-based spec recovery works best when paired with a verifier or program analysis. SpecGen gets verifiable JML specs for 279 of 385 programs. An industrial COBOL/PL-I requirements extractor reports 93% agreement with experts. For behavioral equivalence between original and reimplementation, the field has converged on differential testing, fuzzing and symbolic execution loops that feed counterexamples back to the LLM. PCodeTrans, Fluorine, RustAssure, IBM's COBOL→Java tooling and Decaf all follow this pattern. No mature benchmark yet covers "spec from UI or binary → independent reimplementation".

### Cited Findings
- **SpecGen** (ICSE 2025; arXiv 2401.08807): conversational LLM spec generation plus four mutation operators and heuristic selection of verifiable specs. 279/385 programs got verifiable specs, vs 247 for AutoSpec (best LLM baseline) and 98 for Houdini (best non-LLM). Daikon was also outperformed — [SpecGen arXiv](https://arxiv.org/html/2401.08807v5); [ICSE 2025 listing](https://conf.researchr.org/details/icse-2025/icse-2025-research-track/173/SpecGen-Automated-Generation-of-Formal-Program-Specifications-via-Large-Language-Mod)
- **Business-requirements extraction from COBOL/PL-I** (ACL 2026 Industry Track, pp. 43–55): grammar-based parsing plus control- and data-flow analysis produce an enriched IR, and an LLM emits structured JSON rules. 93% agreement with expert-authored business rules and about 70% less documentation effort, in a financial setting — [ACL Anthology 2026.acl-industry.4](https://aclanthology.org/2026.acl-industry.4/)
- **Reversa** (arXiv 2605.18684, 2026): "reverse documentation engineering" turns legacy systems into operational specs for AI coding agents, with traceability, confidence levels and explicit gaps as part of the spec contract — [Reversa arXiv](https://arxiv.org/pdf/2605.18684)
- **Formal spec extraction from documents** (arXiv 2504.01294, Apr 2025): 603 specs from 37 documents across three OSS projects. Evaluated GPT-4o, Claude and Llama — [arXiv 2504.01294](https://arxiv.org/abs/2504.01294v1)
- **RustPrint** (arXiv, May 2026): generates architecture documentation from a C repo as a migration blueprint, then compares docs regenerated from the Rust output against the source docs to find mismatches to repair. This is a "spec as intermediate representation" pattern — [Emergent Mind summary of 2605.14634](https://www.emergentmind.com/papers/2605.14634)
- **TestWeaver** (ICSE 2026; arXiv 2508.01255): regression test generation that gives the LLM backward slices, nearby tests and per-line runtime variable values. Grows coverage faster and produces more effective tests than SOTA — [TestWeaver arXiv](https://arxiv.org/html/2508.01255v1)
- **Panta** (ICSE 2026): static CFG plus dynamic coverage feedback. +26% line and +23% branch coverage over SOTA — [search summary](https://arxiv.org/pdf/2506.19287v1) (snippet-level)
- A 2025 study found LLM test generation trails traditional tools on coverage but **significantly outperforms them on mutation score** — [search summary](https://arxiv.org/html/2407.00225v3) (snippet-level; attribution to this specific URL not verified)
- **Differential testing for translations:**
  - **Fluorine** (Eniser et al., arXiv 2405.11514): cross-language differential fuzzer checking I/O equivalence of C/Go → Rust translations without existing tests. The best LLM translated 47% of benchmarks. Testing was done on function-level extracts because whole projects do not fit in context — [arXiv 2405.11514](https://arxiv.org/html/2405.11514v3)
  - **RustAssure** (arXiv 2510.07604): differential symbolic testing of LLM-transpiled C→Rust code; divergences are fed back for re-transpilation — [RustAssure](https://arxiv.org/pdf/2510.07604)
  - **IBM COBOL→Java** (arXiv 2504.10548): symbolic execution generates COBOL unit tests with mocked externals, which are converted to JUnit to check the translated Java (watsonx Code Assistant for Z) — [IBM Research](https://research.ibm.com/publications/automated-testing-of-cobol-to-java-transformation)
  - **CINDER** (Vanderbilt): contract-aware differential testing with Clopper–Pearson confidence intervals plus Z3 bit-vector equivalence checking, so overflow and wraparound behavior is modeled correctly — [Vanderbilt IR](https://ir.vanderbilt.edu/items/e24cdd40-6e82-4048-a426-5b97a8c6edbf)
- **Binary-level differential validation:** PCodeTrans swaps the recompiled function into the original binary and diffs runtime traces, reaching 99.55% / 99.89% behavioral consistency on coreutils and binutils. Decaf uses byte-distance and a learned assembly-equivalence reranker as a proxy oracle, reaching 70.9% byte-exact recompilation — [PCodeTrans](https://arxiv.org/abs/2603.14855?context=cs); [Decaf](https://arxiv.org/pdf/2605.11501)

### Inferences
- A reimplementation platform should treat the original program as the oracle. Record traces and I/O from it to synthesize characterization tests (TestWeaver-style runtime-value prompts). Run differential fuzzing or symbolic execution between the original and the new implementation (Fluorine, RustAssure, CINDER). Feed counterexamples back to the agent. Mutation score is a better quality gate for LLM-written tests than coverage.
- Natural-language spec recovery should carry traceability and confidence levels (Reversa) so humans can review gaps. Formal specs (JML/ACSL) are feasible for small units (SpecGen) but have not been shown at repo scale.

### Gaps
- No benchmark was found that measures end-to-end "observe a black-box app (UI, binary, API traffic) → recover a spec → reimplement → pass hidden behavioral tests".
- I found no characterization- or snapshot-test generation papers specifically. Numbers for Panta and the mutation-score study come from snippets only.
- Spec-recovery accuracy for UI-only inputs (screens to requirements) was not found.

---

## 3. Repository-level generation and translation benchmarks relevant to rebuilding whole apps

### Takeaway
Building whole libraries or apps from a spec is still far from solved. On Commit0 (spec plus tests → library), the best 2024 agent passed about 43% of tests on the lite split and 15% on the full split. NL2Repo-Bench (Dec 2025; ICML 2026) caps at about 40% test pass rate, and only 3–5 of 104 repos fully pass. RepoTransBench caps at 32.8% success, with dynamic→static translation under 10%. Seeing the tests matters a great deal: Claude Code on NL2Repo goes from 40.2% to 59.4% with tests visible. Frontier closed models lead open-weight models by about 10–20 points on repo-scale tasks.

### Cited Findings
- **Commit0** (Zhao et al., Cornell + Cohere; arXiv 2412.01769, Dec 2024): 54 Python libraries, lite split of 16. The agent gets an API spec document plus interactive unit tests, and is evaluated by unit-test pass rate — [Commit0 PDF](https://export.arxiv.org/pdf/2412.01769)
  - SDE-I agent on lite, stages 1→3 (stage 3 = unit-test feedback): Claude 3.5 Sonnet 17.80% → 29.30% (stage-3 cost $99.39). DeepSeek-V2.5 16.55% → 25.43%. Llama-3.1-405B 8.08% → 4.95%. Full split, stage 1: Claude 3.5 Sonnet 6.12% ($20.46) — [Commit0](https://export.arxiv.org/pdf/2412.01769)
  - OpenHands with test IDs and lint commands: **42.95% on lite and 15.25% on all**. No library was fully reproduced. Test-time scaling (best-of-n per module) improves the pass rate — [Commit0](https://export.arxiv.org/pdf/2412.01769)
- **NL2Repo-Bench** (arXiv 2512.12730, Dec 2025; ICML 2026 poster): 104 tasks, spec of about 18.8K tokens on average, target repos of 300–120K LOC. The agent gets only a requirements doc and an empty workspace and must ship an installable Python library — [NL2Repo-Bench](https://arxiv.org/html/2512.12730v1); [ICML 2026](https://icml.cc/virtual/2026/poster/60772)
  - Average test pass rate (fully passed of 104): Claude-Sonnet-4.5 via Claude Code 40.2% (3); via OpenHands 39.9% (3); via Cursor 39.2% (4); Claude-Sonnet-4 37.0% (5); Gemini-3-pro (Cursor) 34.2% (3); **DeepSeek-V3.2 27.6% (1); Kimi-K2 22.7% (3); DeepSeek-V3.1 22.2%; GPT-5 21.7%; Qwen3-Instruct 17.9%; GLM-4.6 17.5% (2); Qwen3-Thinking 13.8%** — [NL2Repo-Bench](https://arxiv.org/html/2512.12730v1)
  - Failure modes: GPT-5 never calls finish in 84.5% of tasks, usually waiting for user input, and averages 78.4 turns vs 181.6 for Claude-Sonnet-4.5. Qwen3-Thinking terminates early in 49.0% of tasks. Other failures include missing `__init__.py` / ImportError and signature mismatches with the hidden tests. **Making the test suite visible raised Claude Code from 40.2% to 59.4% and from 3 to 18 fully passed tasks** — [NL2Repo-Bench](https://arxiv.org/html/2512.12730v1)
- **RepoTransBench** (arXiv 2412.17744 v2, Dec 2025): 1,897 real repo samples across 13 language pairs with executable tests, plus the RepoTransAgent ReAct framework — [RepoTransBench v2](https://arxiv.org/html/2412.17744v2)
  - Success rate / compile rate with RepoTransAgent: Claude-Sonnet-4 32.8% / 54.8%; GPT-4.1 32.8% / 53.3%; DeepSeek-Chat 22.5% / 36.5%; Qwen3-235B-think 19.1% / 36.0%; Qwen3-235B 16.9%; o3-mini 12.0%; Gemini-2.5-Flash-Lite 11.3%; DeepSeek-Reasoner 1.2%. Translation-only (no agent) gives 0.0% SR for most models. The agent adds up to +21.5 pp over error-feedback alone — [RepoTransBench v2](https://arxiv.org/html/2412.17744v2)
  - Direction matters: Python→Java 0.0–7.0%, Python→C++ 0.0–9.9%, Python→Rust 1.2–26.3%, vs about 45–63% for static→dynamic pairs. The v1 preprint had a best Success@1 of only 7.33% across 11 LLMs — [RepoTransBench](https://arxiv.org/html/2412.17744v2)
- **C→Rust at repository scale:**
  - Rustine (arXiv 2511.20617): 2,323 C programs, 100% compilable, 87% functional equivalence on test assertions — [Rustine](https://arxiv.org/html/2511.20617v1)
  - EvoC2Rust (ICSE-SEIP 2026): about +17% syntax and +14% semantic accuracy over the best LLM baseline — [arXiv 2508.04295](https://arxiv.org/pdf/2508.04295v2)
  - ORBIT (Apr 2026) notes that out-of-the-box agents produce translations that look right but are incomplete — [alphaXiv](https://www.alphaxiv.org/abs/2604.12048)
  - DepTrans (FSE Companion 2026) targets unresolved cross-file references — [arXiv 2604.02852](https://arxiv.org/html/2604.02852v1)
  - RustRepoTrans: 375 tasks — [review](https://www.themoonlight.io/en/review/repository-level-code-translation-benchmark-targeting-rust)
- **Web apps from spec or screenshot:**
  - **WebGen-Bench** (NeurIPS 2025 oral; arXiv 2505.03733): websites built from scratch, judged by 647 tests run by a web-navigation agent. Best framework plus model was Bolt.diy + DeepSeek-R1 at 27.8%. Qwen2.5-Coder-32B fine-tuned on Bolt.diy trajectories from WebGen-Instruct (6,667 instructions) reached 38.2%, beating the best proprietary model — [WebGen-Bench](https://huggingface.co/papers/2505.03733); [NeurIPS](https://neurips.cc/virtual/2025/oral/121452)
  - **Design2Code** (Si et al., NAACL 2025): 484 real webpages, screenshot → HTML. GPT-4o was best. Models still struggle with recalling visual elements and with layout. Human judges weight high-level visual similarity differently from the automatic metrics — [Design2Code (NSF PAR)](https://par.nsf.gov//servlets/purl/10591120). Follow-ons cover interaction and dynamics: ArtifactsBench, FullFront, WebCode2M — [Emergent Mind summary](https://www.emergentmind.com/topics/design2code-benchmark)
- **SWE-bench family (issue resolution, a proxy for maintaining large codebases):**
  - SWE-bench Pro (Scale), standardized public set, Sep 2026 snapshot (aggregator): Muse Spark 1.1 61.5%, GPT-5.4 (xHigh) 59.1%, Claude Opus 4.6 (thinking) 51.9%, Claude Opus 4.5 45.9%. The private commercial subset is lower (max about 51.5%) — [morphllm SWE-bench Pro summary](https://www.morphllm.com/swe-bench-pro); [Scale leaderboard](https://labs.scale.com/leaderboard/swe_bench_pro_public_v2). Aggregator numbers; vendor-reported numbers above 79% for newer Claude models could not be verified.
  - SWE-bench Verified reportedly shows contamination for frontier models, and OpenAI stopped reporting it, per an aggregator — [morphllm open-source ranking](https://www.morphllm.com/best-open-source-coding-model-2026) (secondary)
  - Open-weight SWE-bench Verified, aggregator-reported and scaffold-dependent: Qwen3-Coder-480B about 67–70%, Kimi K2 65.8% single attempt / 71.6% multi, GLM-4.6 about 68%, DeepSeek-V3.2 about 60–70% — [llmrun.dev](https://llmrun.dev/benchmark/swe-bench-verified); [morphllm](https://www.morphllm.com/best-open-source-llm) (secondary; not verified against model cards)
- **AgentRE / CrackMe** results in §1 show the same pattern in agentic RE: GPT-5.5 > Claude Opus 4.7 > Kimi K2 — [CrackMeBench](https://arxiv.org/html/2605.10597v1)

### Inferences
- Rebuilding a whole app is, in benchmark terms, a Commit0/NL2Repo-type task. Expect about 40% hidden-test pass rate from today's best agents if the spec alone is given, and about 60% if the tests are visible. The platform should therefore produce an executable test oracle from the original program (§2) and give it to the generating agent. This is the single largest lever measured.
- Translating to static, strongly typed targets (Java, C++, Rust) from dynamic sources is the hardest direction. Prefer skeleton-first (EvoC2Rust), dependency-guided generation (DepTrans), and architecture docs as a blueprint (RustPrint).
- Scaffold matters as much as model: OpenHands gave +13.65 pp on Commit0 lite, RepoTransAgent gave +21.5 pp, and NL2Repo shows GPT-5 failing mainly through agent-protocol issues such as never calling finish.

### Gaps
- No Commit0 leaderboard results for 2025–2026 frontier agents were retrieved. The paper's numbers date from 2024 models.
- No authoritative, single-protocol scores for GLM-5, Kimi K2.5/K2.6 or DeepSeek V4 on repo-level benchmarks were found.
- Design2Code numbers for 2025–2026 models, and multi-page or interactive app-cloning benchmarks with results, were not retrieved.

---

## 4. Fine-tuning recipes: datasets, base models, compute, RL with execution rewards, distillation

### Takeaway
Decompilation models use a consistent recipe:
1. Compile permissively licensed C/C++ (ExeBench, Decompile-Bench, GitHub) with GCC and Clang at O0–O3.
2. Strip the binaries and lift them with Ghidra or IDA.
3. Dedup with MinHash, giving 0.3M–5M+ function pairs.
4. Run SFT on a 1.3B–33B code base (DeepSeek-Coder, Qwen2.5/3-Coder, Yi-Coder, CodeGemma, LLM4Decompile).
5. Run GRPO with compile, execute and test rewards on 10K–50K samples.
6. At inference, sample N and rerank with compiler or byte-level feedback.

Agentic SWE models follow the same idea at repo scale. They use executable environments (SWE-Gym 2.4K, R2E-Gym, SWE-smith 50K) with SFT on a few hundred to thousands of trajectories, or RL on test outcomes. Compute ranges from under $20 (small LoRA-style decompiler fine-tune) to a few thousand GPU-hours.

### Cited Findings
- **Data construction (decompilation):**
  - SK²Decompile: ExeBench plus Decompile-Bench C, GCC and Clang O0–O3, x86 Linux, stripped, IDA pseudocode, clang-format normalization, MinHash-LSH dedup. About 5M samples, about 5B tokens total — [SK2Decompile](https://arxiv.org/pdf/2509.22114)
  - Decompile-Bench: about 2M pairs from about 100M, 450 GB of binaries — [Decompile-Bench](https://arxiv.org/html/2505.12668v2)
  - CodeInverter: 8.69M samples with CFG and data maps — [CodeInverter](https://arxiv.org/html/2503.07215v2)
  - Idioms realtype: 154K train functions; ExeBench 2.38M — [Idioms](https://arxiv.org/html/2502.04536v2)
  - AutoDecompiler: about 300K SFT plus 10K RL — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
  - ReSym: 113,696 binaries from 7,416 projects — [ReSym](https://www.cs.purdue.edu/homes/lintan/publications/resym-ccs24.pdf)
- **Base models used:**
  - DeepSeek-Coder 1.3B/6.7B/33B (LLM4Decompile, AutoDecompiler)
  - Yi-Coder-9B (LLM4Decompile-9B-v2) — [GitHub](https://github.com/albertan017/LLM4Decompile)
  - Codestral-22B family (22B-v2 — note: the base was not explicitly confirmed in this session)
  - Qwen3-Coder-30B (AutoDecompiler)
  - Qwen2.5-Coder-7B (ReCopilot)
  - Qwen3-32B (Decaf reranker)
  - CodeGemma-2B/7B and CodeLlama-7B/34B (Idioms, GenNm)
- **RL with execution rewards:**
  - SK²Decompile: GRPO in veRL; compile reward via Psyche-C header synthesis; naming reward = embedding similarity — [SK2Decompile](https://arxiv.org/pdf/2509.22114)
  - AutoDecompiler: multi-turn GRPO with graded execution reward (-1 / -0.6 / -0.3 / +1) plus AST and data-flow terms; +5.5 pp from 3-turn RL — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
  - D-LiFT: RL with an accuracy-gated readability score — [D-LiFT](https://arxiv.org/html/2506.10125v2)
  - **SWE-RL** (Meta; NeurIPS 2025): RL on Llama-3.3-70B with a rule-based reward (difflib similarity to the oracle patch; -1 for malformed output). 41.0% SWE-bench Verified. Generalizes to out-of-domain tasks, whereas the SFT baseline degraded — [SWE-RL arXiv 2502.18449](https://arxiv.org/pdf/2502.18449)
  - **DeepSWE** (Agentica + Together; rLLM): pure RL on Qwen3-32B with about 4,500 R2E-Gym tasks, **6 days on 64 H100s**. Pass@1 42.2% (from 23% after 200 RL steps), Pass@16 71.0%, about 59% with test-time scaling — [Together AI blog](https://together.ai/blog/deepswe)
- **SFT on agent trajectories, distillation from frontier models:**
  - **SWE-Gym** (ICML 2025): 2,438 Python task instances with executable environments. Fine-tuning Qwen2.5-Coder-32B on only 491 trajectories gave up to +19% absolute. With verifiers: 32.0% Verified and 26.0% Lite — [SWE-Gym PMLR](https://proceedings.mlr.press/v267/pan25g.html)
  - **SWE-smith** (NeurIPS 2025): 50K task instances (about 52K in the repo) from 128 repos. SWE-agent-LM-32B (Qwen2.5-Coder-32B) at 40.2% Pass@1 on Verified — [SWE-smith](https://huggingface.co/papers/2504.21798); [GitHub](https://github.com/swe-bench/swe-smith)
  - **WebGen-Instruct**: Qwen2.5-Coder-32B trained on Bolt.diy trajectories reached 38.2% on WebGen-Bench, beating the best proprietary model — [WebGen-Bench](https://huggingface.co/papers/2505.03733)
  - **ReCopilot**: SFT CoT data generated by DeepSeek-V3 (distillation) plus DPO on failure/success pairs; about 7.1K A800 GPU-hours — [ReCopilot](https://arxiv.org/pdf/2505.16366)
- **Inference-time search as a substitute for training:** Decaf argues that compiler feedback plus search beats "more data, more training". Its reranker also boosts weaker generators; LLM4Decompile with reranking reaches about 73.5% functional correctness on some splits — [Decaf](https://arxiv.org/pdf/2605.11501)

### Inferences
- A practical recipe for a specialized reimplementation model:
  1. Start from Qwen3-Coder-30B-A3B or Qwen2.5/3-Coder-7B–32B, or DeepSeek-Coder for small sizes.
  2. Build multi-million-pair corpora by compiling permissive OSS at O0–O3 with GCC and Clang (and MSVC if Windows matters). Lift with Ghidra, which is free and scales; IDA is used in many papers but is licensed.
  3. Run SFT, then GRPO with compile, execute and differential-test rewards on 10–50K held-out functions.
  4. Add a learned reranker or byte-distance reranking at inference.
  5. Distill reasoning traces from a frontier model (DeepSeek-V3/R1 used in ReCopilot) for comprehension and naming.
- Budget anchors: a few thousand GPU-hours for SFT plus RL at 7–32B (ReCopilot 7.1K A800-h; DeepSeek 6 days × 64 H100 ≈ 9.2K H100-h). Rerankers at 32B cost about 2 weeks on 8×B200 each.

### Gaps
- Few papers report total GPU-hours or dollar cost. LLM4Decompile V1.5/V2, Idioms, SK²Decompile and AutoDecompiler give hardware but not totals.
- No published recipe was found for jointly training binary comprehension, spec extraction and reimplementation in one model.
- No license or legal analysis of training on compiled OSS binaries was covered by these sources.

---

## 5. Known limitations and mitigations (context length, hallucination, tool-use loops, verification)

### Takeaway
The main failure modes are:
- Semantic hallucination in decompiled code: readable but wrong; DecompileBench measures 52.2% lower functional correctness than commercial decompilers.
- Collapse at higher optimization levels.
- Hallucinated user-defined types.
- Context limits forcing function-level work.
- Long-horizon agent failures: premature termination, not calling finish, loss of global coherence, broken imports.
- Overconfident reliance on decompiler output.
- Possible memorization inflating benchmark scores.

The mitigations that work are execution-grounded: compile/run feedback loops, differential testing against the original, sampling plus reranking, Prolog/analysis cross-checking, call-graph context, test visibility, and accuracy-gated rewards.

### Cited Findings
- **Readability vs correctness trade-off:** LLM decompilers beat commercial tools on understandability but have 52.2% lower functional correctness; Hex-Rays loses 36.11% correctness at -O3 — [DecompileBench](https://arxiv.org/abs/2505.11340). Ghidra hits 61.51% on ExeBench vs 14.48% on HumanEval, while LLMs show the reverse pattern — [AutoDecompiler](https://arxiv.org/html/2606.16162v1)
- **Optimization-level collapse:** LLM4Decompile-Ref goes 67.07% (O0) → 28.32% (O3); Idioms 70.73% → 10.62% — [SK2Decompile Table 1](https://arxiv.org/pdf/2509.22114)
- **Hallucinated constructs:** neural decompilers can omit critical conditions (e.g., a missing break) while looking idiomatic; the base model hallucinates UDTs. Mitigation is sampling N=32 plus reranking (60% → 88% oracle@32; 59.1% → 83.9% actual) — [Decaf](https://arxiv.org/pdf/2605.11501)
- **Token limits and uncertainty:** ReSym uses a Prolog-based algorithm to aggregate and cross-check multiple LLM queries to suppress hallucination — [ReSym](https://www.cs.purdue.edu/homes/lintan/publications/resym-ccs24.pdf). GenNm includes caller and callee names within token limits — [GenNm](https://ndss-symposium.org/wp-content/uploads/2025-276-paper.pdf). Fluorine evaluated function-level extracts because whole projects do not fit in context — [Fluorine](https://arxiv.org/html/2405.11514v3)
- **Refining bad input rarely works:** D-LiFT improved only 8.02% of functions Ghidra had decompiled inaccurately, vs 86.2% of accurate ones — [D-LiFT](https://arxiv.org/html/2506.10125v2)
- **Long-horizon agent failures:**
  - NL2Repo: GPT-5 never calls finish in 84.5% of tasks; Qwen3-Thinking stops early in 49%; also broken imports and missing `__init__.py` — [NL2Repo-Bench](https://arxiv.org/html/2512.12730v1)
  - CrackMeBench: agents time out after finding the answer site, overfit to the visible example, and over-trust decompiler output — [CrackMeBench](https://arxiv.org/html/2605.10597v1)
  - Commit0: the SDE-I agent repeatedly generates the same fix, while OpenHands explores alternatives (+13.65 pp) — [Commit0](https://export.arxiv.org/pdf/2412.01769)
- **Incomplete translations:** out-of-the-box agents produce C→Rust translations that look right but are incomplete — [ORBIT](https://www.alphaxiv.org/abs/2604.12048). LLMs leave cross-file references unresolved — [DepTrans](https://arxiv.org/html/2604.02852v1)
- **Memorization and contamination:** naming gains from LLM refinement did not depend on the dataflow, types or names in the input, suggesting model priors drive the gains — [arXiv 2609.17236](https://arxiv.org/abs/2609.17236). Decompile-Bench-Eval adds post-2025 GitHub repos to limit leakage — [Decompile-Bench](https://arxiv.org/html/2505.12668v2). SWE-bench Verified is reportedly contaminated for frontier models — [morphllm](https://www.morphllm.com/best-open-source-coding-model-2026) (secondary)
- **Output-format fragility:** ReCopilot produced valid structured JSON only 92% of the time (e.g., predicted non-existent types) — [ReCopilot](https://arxiv.org/pdf/2505.16366)
- **Verification oracles that work:**
  - re-executability and I/O tests (HumanEval-Decompile, ExeBench)
  - byte-exact recompilation match (Decaf)
  - differential trace comparison after hot-swapping into the original binary (PCodeTrans)
  - symbolic and differential testing for translations (RustAssure, Fluorine, CINDER, IBM)
  - verifier-in-the-loop spec mutation (SpecGen)
  - visible test suites for generation (NL2Repo: +19.2 pp)

### Inferences
- Design the platform so that no LLM output is trusted without an execution oracle. Use the original artifact (binary, service, UI) as the ground truth and add equivalence gates at function, module and system level.
- Use hybrid pipelines: a classic decompiler for correctness, the LLM for readability, naming and types, and analysis-based cross-checks (ReSym-style) for UDTs. A "Ghidra + recompilable exporter" baseline already reaches about 80% on ExeBench -O2 per Decaf.
- For long-horizon generation, enforce explicit completion criteria (all tests pass), an anti-early-termination protocol, packaging and import checks, and diversity in repair attempts.
- Evaluate on post-cutoff code or code written in-house to avoid memorization-inflated results.

### Gaps
- No quantitative study was found on context-length scaling (e.g., 128K–1M token windows) for whole-binary or whole-repo comprehension.
- Robustness to obfuscation, packing and anti-decompilation in LLM decompilers was not covered by retrieved sources.
- No data was found on legal and IP risk (clean-room reimplementation provenance, memorized code leakage) for these systems. Commit0 measured 10-gram overlap with the reference, but no numbers were extracted.
