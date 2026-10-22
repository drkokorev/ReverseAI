# Legal Framework and Market for an AI Clean-Room Reimplementation Platform (as of October 2026)

Note: these are research notes, not legal advice. Research date: 2026-10-20. Items marked "[background, not re-verified this session]" come from well-established public record. They were not re-fetched during this session, so check them against the primary text before relying on them.

## 1. Legal doctrine of clean-room design and independent reimplementation (key cases; protected vs. unprotected)

### Takeaway
In the US and EU, the law protects the **expression** of software: source and object code, and sometimes detailed structure or UI expression. It does not protect **functionality, ideas, algorithms, programming languages or data/file formats**. Intermediate copying such as disassembly, done to reach unprotected functional elements, has been held fair use in the US (Sega, Connectix). The Supreme Court decided that Google's reuse of the Java API declarations was fair use. It did not decide whether APIs are copyrightable. A clean room is therefore an **evidentiary** device that proves independent creation. It is not a legal requirement in itself.

### Cited Findings
- 17 U.S.C. §102(b): copyright does not extend to "any idea, procedure, process, system, method of operation, concept, principle, or discovery". This is the statutory basis for treating functionality as unprotectable. — [17 U.S.C. §102, Cornell LII](https://www.law.cornell.edu/uscode/text/17/102) [background, not re-verified this session]
- *Sega v. Accolade*, 977 F.2d 1510 (9th Cir. 1992). Disassembling Sega's code to learn the interface requirements for compatible games was fair use, because disassembly was the only way to access unprotected functional elements and there was a legitimate reason. — [Wikipedia: Sega v. Accolade](https://en.wikipedia.org/wiki/Sega_v._Accolade) [background, not re-verified this session]
- *Sony v. Connectix*, 203 F.3d 596 (9th Cir. 2000). Repeated intermediate copying of the PlayStation BIOS while building a competing emulator (Virtual Game Station) was fair use, and the final product was "modestly transformative". — [Wikipedia: Sony v. Connectix](https://en.wikipedia.org/wiki/Sony_Computer_Entertainment,_Inc._v._Connectix_Corp.) [background, not re-verified this session]
- *Atari v. Nintendo*, 975 F.2d 832 (Fed. Cir. 1992). Reverse engineering can be fair use, but Atari lost because it obtained Nintendo's code from the Copyright Office under false pretenses. The lesson: **the material must be lawfully obtained**. — [Wikipedia: Atari Games Corp. v. Nintendo](https://en.wikipedia.org/wiki/Atari_Games_Corp._v._Nintendo_of_America_Inc.) [background, not re-verified this session]
- *Google LLC v. Oracle America*, 593 U.S. 1 (Apr. 5, 2021). Google's copying of about 11,500 lines of Java SE API declaring code was fair use. The Court assumed copyrightability without deciding it. — [US Supreme Court opinion PDF](https://www.supremecourt.gov/opinions/20pdf/18-956_d18f.pdf) [background, not re-verified this session]
- *Lotus v. Borland*, 49 F.3d 807 (1st Cir. 1995), affirmed by an equally divided Court in 1996. The Lotus 1-2-3 menu command hierarchy was an uncopyrightable "method of operation". This is relevant to UI and command reimplementation, but other circuits apply abstraction-filtration-comparison instead. — [Wikipedia: Lotus v. Borland](https://en.wikipedia.org/wiki/Lotus_Dev._Corp._v._Borland_Int%27l,_Inc.) [background, not re-verified this session]
- Phoenix Technologies (1984) and Compaq (1982) reimplemented the IBM PC BIOS using two teams. One team wrote specifications and a separate team with no exposure to the IBM code implemented from those specs. This is the canonical clean-room model. One writer says Compaq's reverse engineering of the BIOS cost about $1M. — [Matt Hopkins, Apr 15 2026](https://matthopkins.com/technology/clean-room-loophole-agentic-coding-software-copyright/); [Wikipedia: Clean-room design](https://en.wikipedia.org/wiki/Clean-room_design) [background]
- *SAS Institute v. World Programming*, CJEU C-406/10 (May 2, 2012). The functionality of a program, the programming language and data file formats are not protected under the Software Directive. A licensee may observe, study and test a program to learn its ideas and principles, and contract cannot prevent this. However, copying manuals or documentation may infringe the InfoSoc Directive. — [EUR-Lex CELEX 62010CJ0406](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62010CJ0406) [background, not re-verified this session]
- *BSA v. Ministry of Culture* (CJEU C-393/09, Dec 22, 2010). A graphical user interface is not a "computer program" under the Software Directive, but it can be protected as an ordinary copyright work if it is original. This means UI and look-and-feel carry a separate risk in the EU. — [EUR-Lex CELEX 62009CJ0393](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62009CJ0393) [background, not re-verified this session]
- *Top System v. Belgian State* (CJEU C-13/20, Oct 6, 2021). A lawful acquirer may decompile a program to correct errors under Art. 5(1), within limits. This applies even outside the Art. 6 interoperability route. — [EUR-Lex CELEX 62020CJ0013](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62020CJ0013) [background, not re-verified this session]
- Clean-room methodology exists to prevent derivative works. In the chardet dispute, the rewriter argued that independence can also be shown by measurement, citing JPlag similarity of at most 1.29% against the previous release. — [Simon Willison, Mar 5 2026](https://simonwillison.net/2026/Mar/5/chardet/)

### Inferences
- **Protected (do not reproduce):** source and object code; literal documentation and manual text; original UI artwork, icons, sounds and other assets; trademarks and trade dress, including product name and logo; patented methods; trade secrets obtained in breach of an NDA or license.
- **Generally not protected (may reimplement):** behavior and functionality; algorithms as ideas; file formats and wire protocols; programming languages; command/menu hierarchies in some circuits; API compatibility, which is fair use in the US after *Google v. Oracle* and generally unprotected in the EU after *SAS*. API copyrightability itself remains formally unresolved in the US.
- Lessons from the case law for product design:
  - Obtain inputs lawfully. Atari lost on this point.
  - Use reverse engineering only to extract unprotected elements.
  - Keep the output product dissimilar in expression.
  - Avoid confusing branding. Trademark risk is independent of copyright.

### Gaps
- Patents: no 2025-2026 sources were researched. A clean room gives **no defense** against patent infringement, because independent creation is not a defense to patent infringement. A freedom-to-operate search is needed for each target product.
- I did not find any post-2021 US appellate decision applying *Google v. Oracle* to a full commercial reimplementation.

## 2. Jurisdictions: US, EU, Russia; how EULA anti-reverse-engineering clauses interact

### Takeaway
- **EU:** decompilation for interoperability (Art. 6) and observation/study/testing (Art. 5(3)) **cannot be overridden by contract** (Art. 8). However, information obtained under Art. 6 cannot be used to build a substantially similar program.
- **Russia (Art. 1280 ГК РФ):** very similar rules. Decompilation is allowed only for interoperability, and its results cannot be used to develop a program "substantially similar in form".
- **US:** there is no statutory override of contracts. Two appellate courts (Bowers, Fed. Cir.; Davidson v. Jung, 8th Cir.) enforced EULA bans on reverse engineering against preemption arguments. DMCA §1201(f) provides a narrow interoperability exemption from the anti-circumvention rules.

### Cited Findings
**US**
- DMCA §1201(f) allows circumvention of a technological measure to identify and analyze elements needed for interoperability of an independently created program, if those elements are not readily available, and allows sharing of the resulting information for that purpose only. — [17 U.S.C. §1201, Cornell LII](https://www.law.cornell.edu/uscode/text/17/1201) [background, not re-verified this session]
- The ninth triennial §1201 proceeding concluded in October 2024. The Librarian adopted the Register's Recommendation in full. There were 11 petitions for new or expanded exemptions and 37 renewal petitions. A proposed exemption for AI "trustworthiness" research was denied. — [USCO 2024 1201 page](https://copyright.gov/1201/2024/); [USCO NewsNet 1057](https://copyright.gov/newsnet/2024/1057.html); [Stones Law](https://www.stoneslaw.net/copyright-office-denies-proposed-ai-security-research-exemption-in-triennial-rulemaking-under-dmca)
- The 2024 exemptions run until October 2027. No information on the tenth (2027) cycle's software exemptions was found. — [USCO 1201](https://copyright.gov/1201/2024/)
- *Bowers v. Baystate* (Fed. Cir. 2003): copyright did not preempt a shrink-wrap license ban on reverse engineering. A commentary notes that contract damages for such a breach may often be de minimis. — [Aber Law Firm](https://www.aberlawfirm.com/reverse-engineering-software-for-interoperability-law-update-july-2010); [vLex / Washington J.L.](https://law-journals-books.vlex.com/vid/7-wash-j-l-936457248)
- *Davidson & Associates v. Jung* (8th Cir. 2005), the Blizzard / bnetd case: contract claims were not preempted, and by agreeing to the EULA/TOU, the defendants waived the DMCA interoperability exception. — [Studicata case brief](https://www.studicata.com/case-briefs/case/davidson-associates-v-jung); [EFF law professors' brief](https://kittens.eff.org/files/filenode/Blizzard_v_bnetd/20040221_law_professor_brief.pdf)
- A practitioner warns that US-style anti-reverse-engineering clauses may need adjustment for EU customers because of the Software Directive. — [Aber Law Firm](https://www.aberlawfirm.com/reverse-engineering-software-for-interoperability-law-update-july-2010)

**EU**
- Directive 2009/24/EC:
  - Art. 5(3): a lawful user may observe, study and test the functioning of the program.
  - Art. 6: decompilation is allowed when indispensable to obtain interoperability information, under these conditions:
    - it is performed by a licensee or authorized person;
    - the information is not previously readily available;
    - it is confined to the necessary parts;
    - the information cannot be used for other goals, cannot be given to others except for interoperability, and cannot be used to develop a program substantially similar in expression.
  - Art. 8: contractual provisions contrary to Art. 6 or to the exceptions in Art. 5(2)-(3) are null and void.
  - [EUR-Lex 32009L0024](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024) [background, not re-verified this session]

**Russia**
- Art. 1280 ГК РФ:
  - п.1: a person lawfully possessing a copy may run it, adapt it solely for functioning on the user's hardware, and fix obvious errors "unless the contract provides otherwise". This proviso attaches to п.1 actions. Archival copies are also allowed.
  - п.2: without consent, the user may study, research and test the program's functioning to determine the ideas and principles underlying any element.
  - п.3: decompilation, by the user or another person on the user's behalf, is permitted when necessary for interoperability of an independently developed program, provided that:
    - (1) the information was not previously available from other sources;
    - (2) only the necessary parts are decompiled;
    - (3) the information is used only for interoperability; it may not be passed to third parties except as necessary for interoperability, and may not be used to develop a program **substantially similar in its form** or for any other infringing act.
  - п.4: application must not unreasonably prejudice the rightholder's legitimate interests or conflict with normal use.
  - [КонсультантПлюс, ст. 1280 ГК РФ](https://www.consultant.ru/document/cons_doc_LAW_64629/3cbc9e0590122df6ade6baf1d39f9ee34411c24a/) — the page notes a revised edition with changes not yet in force. Check the in-force version.

### Inferences
- In the **EU and Russia**, the "contract may override" language attaches to п.1 / Art. 5(1) ordinary-use acts, not to study (п.2 / Art. 5(3)) or interoperability decompilation (п.3 / Art. 6). A EULA ban is likely ineffective against those uses. However, it still counts as a breach-of-contract risk in the US.
- The EU and Russian decompilation exceptions are **interoperability-only**. Using decompiled code to build a functionally *equivalent* replacement product falls outside Art. 6 and п.3 of Art. 1280. A platform targeting "equivalent functionality" should therefore build specs from black-box observation, public documentation, user-owned data and formats, and testing (Art. 5(3) / п.2). Decompilation should be limited to interface and interoperability layers.
- In the US, a customer bound by a EULA that bans reverse engineering faces contract claims even where copyright fair use applies. The platform's terms of service should place on the customer the duty to warrant that it has the right to analyze the target. It should also offer a "black-box only" mode that does not require accepting or breaching a EULA.

### Gaps
- No Russian court practice on Art. 1280 п.3 was gathered. Consultant/Garant commentary was not fetched.
- The status of the tenth (2027) US §1201 rulemaking cycle was not found.
- The US question of whether browsewrap/clickwrap anti-RE terms bind non-licensees, such as a contractor analyzing a public SaaS, was not researched for 2025-2026.

## 3. Specific risks of AI-assisted reimplementation (training exposure, agents reading decompiled code, 2025-2026 debates and cases)

### Takeaway
No court had ruled on an "AI clean room" as of October 2026. The leading real-world test is the **chardet 7.0** relicensing dispute (March 2026). The leading provocation is **Malus "clean room as a service"** (FOSDEM 2026, satirical). The Ninth Circuit's *Doe v. GitHub* decision (Sep 16, 2026) rejected DMCA §1202(b) claims against AI code output but left infringement-by-output open. Separately, purely AI-generated code may be **uncopyrightable** for the customer: the human-authorship rule was left intact when the Supreme Court denied cert in *Thaler v. Perlmutter* on Mar 2, 2026.

### Cited Findings
**The chardet 7.0 case**
- On **Mar 2, 2026**, maintainer Dan Blanchard released chardet 7.0.0 as a "ground-up, MIT-licensed rewrite" of Mark Pilgrim's 2006 LGPL library, keeping the same package name and public API. He later switched the license from MIT to 0BSD. Pilgrim opened issue #327, "No right to relicense this project", two days later. — [Heather Meeker, Apr 9 2026](https://heathermeeker.com/2026/04/09/the-chardet-controversy-open-source-and-the-ai-clean-room/)
- **Process:**
  - Blanchard wrote a design document, then built with Claude Code in an empty repository without access to the old source tree.
  - He instructed Claude not to base anything on LGPL/GPL code.
  - One exception: Claude Code did look at `metadata/charsets.py` from the old codebase.
  - JPlag similarity was at most 1.29% against the prior release, compared with 80-93% between earlier releases.
  - Claude was "likely trained on chardet", which cannot be confirmed.
  - [Simon Willison, Mar 5 2026](https://simonwillison.net/2026/Mar/5/chardet/)
- Blanchard acknowledged that a traditional clean room requires "a strict separation between people with knowledge of the original" and that this did not exist here. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)
- Richard Fontana, a co-author of GPLv3/LGPLv3, commented on Mar 27 that he saw no basis yet for requiring LGPL, because no one had identified copyrightable expression carried over. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/); [Heather Meeker](https://heathermeeker.com/2026/04/09/the-chardet-controversy-open-source-and-the-ai-clean-room/)
- **Heather Meeker's analysis:**
  - Blanchard's decade of exposure "could not be cleansed", so the rewrite was not a true clean room.
  - AI can serve as a "neutral actor" between the specification team and the implementation team.
  - The main error was calling the work independent while shipping it as the next version under the same name.
  - Clean rooms done only to escape copyleft usually create technical debt.
  - [Heather Meeker](https://heathermeeker.com/2026/04/09/the-chardet-controversy-open-source-and-the-ai-clean-room/)

**Malus "clean room as a service"**
- Launched around FOSDEM 2026 by Dylan Ayrey and Mike Nolan after a talk titled "The Death of Open Source".
- Customers upload a dependency manifest. One agent group reads only public documentation and writes specs, and a separate group implements from those specs. Output ships under a "MalusCorp-0" license.
- It is described as **satirical**, intended to highlight licensing tensions rather than to serve as a working legal tool.
- [Elektroda news](https://www.elektroda.com/news/news4169248.html); details from search-result summaries, not fully verified by direct fetch.

**Commentary**
- Commentators note that the model was likely trained on the original. Some argue that AI-written code may be uncopyrightable, so a rewrite could avoid infringing and yet be unprotectable. Several sources flag that no court has tested this fact pattern. — [Adafruit blog, Jun 23 2026](https://blog.adafruit.com/2026/06/23/ai-can-rewrite-open-source-code-but-can-it-rewrite-the-license-too/); [DEV Community: AI license laundering](https://dev.to/pickuma/ai-license-laundering-how-code-generators-strip-open-source-obligations-2i0m); [Hexaware blog](https://hexaware.com/blogs/ai-clean-room-engineering-can-you-legally-rebuild-what-you-can-see/)
- Matt Hopkins (Apr 15, 2026) argues that copyleft, and also proprietary moats, were sustained by the **economic cost** of reimplementation, which agentic coding collapses. — [Matt Hopkins](https://matthopkins.com/technology/clean-room-loophole-agentic-coding-software-copyright/)
- Simon Willison expects "well-funded litigation" once commercial companies see their IP threatened. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)
- A Black Duck audit cited in commentary found that 68% of audited commercial codebases contained license conflicts, up from 56%. — [DEV Community](https://dev.to/pickuma/ai-license-laundering-how-code-generators-strip-open-source-obligations-2i0m) (secondary citation of Black Duck; primary not fetched)

***Doe v. GitHub* (9th Cir., No. 24-7700, decided Sep 16, 2026)**
- The court affirmed dismissal of the DMCA §1202(b) claims. Copilot and Codex "generated new code that never contained CMI", so there was no removal of copyright management information.
- The court rejected the district court's "identicality" requirement. Substantial reproduction with CMI removed could still support a claim.
- The court did not reach whether AI outputs reproducing copyrighted material infringe.
- The training-stage CMI removal theory was not preserved. Contract claims reportedly remain pending.
- [Gibson Dunn](https://www.gibsondunn.com/ninth-circuit-clarifies-limits-of-dmca-liability-for-ai-generated-code/); [Haynes Boone](https://www.haynesboone.com/news/alerts/ai-legal-news-ninth-circuit-rejects-dmca-section-1202(b)-theory); [Ropes & Gray, Sep 2026](https://www.ropesgray.com/en/insights/alerts/2026/09/ninth-circuit-rules-generative-ai-outputs-are-not-stripped-copies-under-the-dmca); [The Next Web](https://thenextweb.com/news/ninth-circuit-github-copilot-dmca-copyright-ruling)

**Copyrightability of AI output**
- The Supreme Court denied cert in *Thaler v. Perlmutter* (No. 25-449) on **Mar 2, 2026**, leaving the D.C. Circuit's human-authorship requirement in place. The level of human involvement needed for protection remains unsettled. — [Reed Smith](https://www.reedsmith.com/our-insights/blogs/viewpoints/102mlpl/supreme-court-denies-certiorari-in-thaler-v-perlmutter-human-only-rule-for-ai/); [Sterne Kessler](https://www.sternekessler.com/news-insights/client-alerts/ip-hot-topic-cert-denied-but-one-thing-is-cert-ain-the-human-authorship-requirement-for-copyright/); [IIPLA](https://iipla.org/news/supreme-court-declines-review-in-landmark-ai-authorship-copyright-case-thaler-v-perlmutter)
- The US Copyright Office's Part 2 report on copyrightability (Jan 2025) says prompts alone are generally insufficient, while human selection, arrangement and modification can be protected. — [USCO Part 2 report](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf) [background, not re-verified this session]

### Inferences
- **Training exposure:**
  - Training exposure ("the model saw the original") is not, under existing doctrine, an automatic disqualifier. Copyright infringement requires copying of protected expression, shown by access plus substantial similarity. Independent creation defeats infringement only if the output is not substantially similar.
  - Proving model "non-access" is impossible for widely published code. Legitimacy must therefore rest on two things: (a) **output dissimilarity evidence**, such as similarity scans against the original where available, plus licensed-code and snippet-match filters; and (b) **process evidence**, meaning the implementer agent never received original code or decompiled output.
  - This mirrors how human clean rooms tolerate engineers with general industry knowledge.
- **Agents reading decompiled code:**
  - This is the highest-risk configuration. It is equivalent to an engineer reading the source, which breaks the clean room for that agent and context.
  - In the EU and Russia, using decompiled information to build a substantially similar program is expressly barred.
  - Decompiled or disassembled material should be confined to an "analysis" agent whose outputs are filtered into abstract specs, and should never enter the implementer context.
- **Customer-side risk:** if output is mostly AI-generated with little human authorship, the customer may not own enforceable copyright in its reimplementation. That weakens its own moat, though not its freedom to operate. This should be disclosed in the terms of service.
- **Relicensing open source:** chardet shows that reputational and community risk is high even when legal risk may be low. Reusing the original name or package and claiming independence is the most criticized pattern. That suggests product defaults of new names and no reuse of the original's identifiers or trademarks.

### Gaps
- No court decision on an AI clean room or an AI-rewritten relicense was found as of Oct 2026.
- No lawsuit was found against Malus or the chardet maintainer. It is unknown whether Pilgrim pursued legal action.
- The EU AI Act and EU copyright angles (TDM opt-outs, Art. 4 DSM Directive) for training on code were not researched in this session.
- The outcome of other pending code and LLM suits beyond *Doe v. GitHub*, such as the remaining contract claims, is unknown.

## 4. Best-practice clean-room process and how an AI platform could automate and document it

### Takeaway
The classic process (Phoenix/Compaq BIOS) has four steps:
1. A "dirty" analysis team studies the target and writes a functional specification that contains no expression.
2. A legal reviewer vets the spec.
3. A "clean" implementation team that has never been exposed to the target implements from the spec only.
4. Everything is logged to prove independence.

AI agents can enforce this separation mechanically: isolated contexts, no shared memory, spec-only channels, and immutable logs. Commentators (Meeker) see AI as a potential "neutral actor" between the teams. Malus demonstrates the architecture, but as satire.

### Cited Findings
- The traditional clean room requires "a strict separation between people with knowledge of the original" and the implementers. — [Simon Willison quoting Blanchard](https://simonwillison.net/2026/Mar/5/chardet/)
- The Phoenix BIOS process used a team that studied the IBM BIOS and wrote specs, and a separate programmer team with no IBM-code exposure that implemented from those specs. — [Wikipedia: Clean-room design](https://en.wikipedia.org/wiki/Clean-room_design) [background]
- Malus architecture: one agent group reads only public documentation and writes specs, a separate group builds from the specs, and the two "never talk to each other". — [Elektroda](https://www.elektroda.com/news/news4169248.html)
- AI can act as a "neutral actor" between specification and reimplementation developers. — [Heather Meeker](https://heathermeeker.com/2026/04/09/the-chardet-controversy-open-source-and-the-ai-clean-room/)
- In chardet, tests were written first and followed by replacement code, based on a design document dated Feb 25, 2026. The output was measured with JPlag. — [Simon Willison](https://simonwillison.net/2026/Mar/5/chardet/)

### Inferences (product-feature design, derived from the findings above)
- **Two-tier agent isolation:**
  - The "Analyst" agents may access the target binary, UI, documentation and traffic, within legal limits per jurisdiction.
  - The "Builder" agents have no access to target artifacts and receive only an approved spec plus black-box conformance tests.
  - Enforce this with separate sandboxes and model sessions, no shared vector store or memory, and network egress controls.
- **Spec firewall:**
  - Automated scrubbing removes code snippets, identifiers, string literals, comments and UI text copied from the target.
  - Specs are expressed as behavior, contracts and test cases. A human reviewer (customer counsel) signs off on each spec.
- **Provenance and audit log:**
  - Hash-chained logs of every input each agent saw, with model and version, prompts, tool calls and spec versions.
  - An exportable "clean-room certificate / evidence pack" for litigation or M&A diligence.
- **Similarity gate:** before release, run code-similarity checks (for example JPlag/MOSS-style, where the original source is available to a separate auditor), open-source license and snippet scanning, and asset and trademark checks.
- **Jurisdiction modes:**
  - EU/RU "interoperability-only decompilation" mode, limited to interface parts with no transfer to Builders.
  - US "black-box / documentation-only" default.
  - Customer attestation of lawful possession of the target and review of its EULA.
- **Residual disclosures:** training-data exposure cannot be eliminated. Mitigate it with output filters ("block suggestions matching public code"), dissimilarity evidence and indemnity limits.

### Gaps
- No published industry standard or certification for AI clean rooms was found.
- No law-firm template for AI clean-room protocols was found in this session.
- Whether courts will give weight to automated agent separation as equivalent to human separation is untested.

## 5. Market: who pays, market size, existing companies and pricing, go-to-market

### Takeaway
The paying market today is overwhelmingly **legacy and application modernization**: mainframe/COBOL, code migration and cloud migration. It is worth about **$22-23B in 2025**, rising to about **$40-51B by 2030-2031** (analyst estimates vary).

Big platforms are commoditizing the tooling:
- AWS Transform's mainframe agent is free.
- Anthropic's Feb 23, 2026 COBOL post moved IBM stock about 13% in a day.

Startups raising money include Mechanical Orchard ($50M Series B, 2024) and Hypercubic ($5.3M seed, Aug 2026). No funded startup positioned explicitly as "AI clean-room reimplementation" was found.

### Cited Findings
**Market size**
- MarketsandMarkets: application modernization services at $22.67B (2025), projected to $51.45B by 2031 (14.6% CAGR). — [MarketsandMarkets](https://www.marketsandmarkets.com/PressReleases/application-modernization-services.asp)
- Technavio (Mar 2026): +$24.97B incremental growth 2025-2030 at 16.2% CAGR, with North America the largest region. — [Technavio](https://www.technavio.com/report/application-modernization-services-market-industry-analysis)
- Meticulous Research (Jun 2024): $40.2B by 2030 at 17.4% CAGR. — [Meticulous Research](https://meticulousresearch.com/pressrelease/752/application-modernization-services-market-2030)
- Another market estimate (secondary, via search) gives $24.98B in 2025 and $56.87B by 2030, or $29.39B in 2026 and $66.21B by 2031, for "legacy modernization". — [Gogloby](https://gogloby.com/insights/legacy-software-modernization-companies/) (vendor-sourced, treat with caution)

**Market signals**
- Anthropic published "Automating Legacy System Modernization with COBOL" on **Feb 23, 2026**, claiming Claude Code can automate the analysis phases that dominate modernization cost. IBM fell about 13% (some report 11%), its largest one-day drop since Oct 2000. — [Gigazine](https://www.gigazine.net/gsc_news/en/20260224-ibm-ai-casualty-anthropic-claude-code-cobol); [Malay Mail/Reuters](https://www.malaymail.com/amp/news/money/2026/02/24/ibm-shares-hit-25-year-low-as-ai-promises-to-update-ageing-mainframe-code/210190); [Puck](https://puck.news/why-ibm-stock-crashed-and-then-bounced-back/)

**Companies and funding**
- **Hypercubic:** $5.3M seed (Aug 18, 2026), led by CIV with YC, Afore and Pioneer Fund. Products are Hopper, an agentic development environment for mainframe, and HyperLoop, AI COBOL modernization with layered verification. — [SiliconANGLE](https://siliconangle.com/2026/08/18/hypercubic-raises-5-3m-map-rewrite-legacy-cobol-apps-ai-agents/); [Hypercubic](https://www.hypercubic.ai/insights/hypercubic-raises-usd5-3m-to-build-the-future-of-mainframe-modernization)
- **Mechanical Orchard:** $50M Series B led by GV (Aug 6, 2024). Reported totals range from $53M to $81M depending on source. It launched the Imogen mainframe modernization platform and a Thoughtworks partnership in Apr 2025. — [Mechanical Orchard](https://mechanical-orchard.com/insights/mechanical-orchard-secures-50-million-to-safely-transition-large-organizations-off-risky-legacy-software); [Pulse 2.0](https://pulse2.com/mechanical-orchard-50-million-series-b-raised-to-help-companies-transition-away-from-legacy-software/)
- **Incumbents:** IBM (watsonx Code Assistant for Z), HCLTech, Capgemini and Accenture offer AI COBOL modernization. — [Gogloby](https://gogloby.com/insights/legacy-software-modernization-companies/)
- **Adjacent funding:** Ema raised $77M (Sep 23, 2026) for AI agents replacing enterprise software and services work. This is evidence of investor appetite for "AI eating enterprise software". — [TechCrunch](https://techcrunch.com/2026/09/23/ema-raises-77m-as-ai-starts-eating-into-enterprise-software-and-services/)

**Pricing**
- **AWS Transform:**
  - The mainframe, VMware and Windows modernization agents and assessment are **free** ("future capabilities may be paid").
  - Custom transformations (code, APIs, frameworks) are paid **per "agent minute"**.
  - The mainframe runtime is billed hourly. The analysis, developer and build tools carry no extra charge beyond infrastructure.
  - [AWS Transform pricing](https://aws.amazon.com/transform/pricing); [AWS Mainframe Modernization pricing](https://aws.amazon.com/mainframe-modernization/pricing); [Qovery analysis](https://www.qovery.com/blog/aws-transform-what-it-does-and-what-it-costs)
- Target-state infrastructure and licensing usually dominate project budgets, not the tooling. — [Qovery](https://www.qovery.com/blog/aws-transform-what-it-does-and-what-it-costs)
- **Malus (satire):** no funding found. — [Elektroda](https://www.elektroda.com/news/news4169248.html)

### Inferences
- **Segments that pay, from most to least proven:**
  1. **Legacy and mainframe modernization**, which has large budgets, SI-led, per-project deals often worth millions.
  2. **Migration off vendor lock-in**, for example replicating a proprietary tool's behavior or data formats. *SAS v. WPL* is the canonical legal precedent for a functional clone.
  3. **Open-source replacement or relicensing of dependencies**, which is legally gray and reputationally toxic after chardet and Malus. Avoid it as a headline use case.
  4. **Interoperability and security research**, which has smaller budgets but strong legal footing (Art. 6, §1201(f), Art. 1280 п.3).
- **Pricing models observed:**
  - Hyperscaler "free agent + paid consumption".
  - Per-agent-minute usage pricing.
  - SI per-project services.
  - Startups combining a platform with services (Mechanical Orchard).
- **Differentiation:** pure code-translation tooling is being commoditized by AWS, Anthropic and IBM. A defensible wedge is **legal-grade provenance**: clean-room evidence packs, similarity gates and jurisdiction-aware workflows, sold to legal and compliance buyers and to SIs. A plausible go-to-market is enterprise contracts plus SI and law-firm partnerships, priced per project or per spec module, with an audit/evidence add-on. These are inferences, not sourced.

### Gaps
- No published pricing was found for Mechanical Orchard, Hypercubic, IBM watsonx Code Assistant for Z, or SI clean-room engagements.
- Gartner and Forrester figures were not accessible.
- No market sizing exists specifically for "clean-room reimplementation" or for interoperability/lock-in-exit tooling. All figures above are for application modernization broadly.
- No Russia-specific market data was found, such as import-substitution (импортозамещение) demand for functional replacements of foreign software. This is a likely relevant segment but was not researched.
