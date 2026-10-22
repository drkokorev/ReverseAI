"""English catalog (the default language). Keys and placeholders match `ru.py` one to one.

Entries are `str.format` templates; a dict holds plural forms (`one`, `other`) chosen by the
`count` parameter. Uppercase labels are written in uppercase here, as the design shows them.
"""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    # Shared words
    "common.none": "none",
    "common.yes": "yes",
    "common.no": "no",
    "common.of": "{part} of {whole}",
    # Pipeline phases (labels in messages) and their short timeline names
    "phase.intake": "Project intake",
    "phase.observe": "Observation",
    "phase.oracle": "Behavior oracle",
    "phase.spec": "Specification",
    "phase.prepare_release": "Release preparation",
    "phase.release": "Release through the barrier",
    "phase.implement": "Implementation",
    "phase.parity": "Parity check",
    "phase.audit": "Audit",
    "phase_done": "Phase “{label}” ({phase}) complete.",
    "stage.intake": "INTAKE",
    "stage.observe": "OBSERVE",
    "stage.oracle": "ORACLE",
    "stage.spec": "SPEC",
    "stage.prepare_release": "PREPARE",
    "stage.release": "BARRIER",
    "stage.implement": "BUILD",
    "stage.parity": "PARITY",
    "stage.audit": "AUDIT",
    "zone_note.dirty": "Sees the original",
    "zone_note.released": "Package past the barrier",
    "zone_note.clean": "Clone code",
    "zone_note.verifier": "Verification reports",
    # Errors shared by the CLI and the console
    "error.intake": "project intake check failed",
    "error.release": "release through the barrier refused",
    "error.policy": "the data policy forbids this model call",
    "error.gateway": "no model responded",
    "error.llm_output": "invalid model response",
    "error.yaml": "invalid YAML",
    "error.phase_order": "complete the “{label}” phase first ({phase})",
    "error.validation": "invalid data ({title}): {summary}",
    "validation.extra_forbidden": "unknown field",
    "validation.missing": "required field is missing",
    "validation.json_invalid": "invalid JSON",
    "validation.string_type": "expected a string",
    "validation.string_too_short": "must not be empty",
    "validation.bool_type": "expected true or false",
    "validation.int_type": "expected an integer",
    "validation.float_type": "expected a number",
    "validation.list_type": "expected a list",
    "validation.dict_type": "expected an object",
    "validation.invalid": "invalid value",
    "validation.more": "and {count} more",
    # Intake gate (project card, observation scope)
    "intake.no_usable_characters": "project name '{name}' has no usable characters",
    "intake.attestation_required": "attestation of lawful access is required",
    "intake.host_not_allowed": "target host '{host}' is not in allowed_domains",
    "intake.product_reuses_brand": "product name '{name}' reuses a brand term",
    "intake.project_exists": "project directory already exists: {path}",
    "intake.observe_needs_sandbox": "submitting forms and probing require card.target_is_sandbox",
    "intake.replay_needs_sandbox": (
        "replaying scenarios on the original requires card.target_is_sandbox"
    ),
    "intake.submit_forms_needs_sandbox": (
        "submit_forms requires a sandbox target (card.target_is_sandbox)"
    ),
    "intake.explorer_domains_subset": (
        "explorer allowed_domains must be a subset of the card's allowed_domains"
    ),
    "intake.start_host_not_allowed": "start_url host '{host}' is not in allowed_domains",
    "intake.probe_needs_sandbox": (
        "probing writes to the target and requires card.target_is_sandbox"
    ),
    "intake.probe_host_not_allowed": "probe host '{host}' is not in allowed_domains",
    "project.busy": (
        "project is busy in another process: {path} (another command or console job is "
        "running). Wait for it to finish and try again."
    ),
    # Barrier
    "release_error.product_name": "spec product name {spec} is not the project's {card}",
    "release_error.no_artifact": "no dirty-zone artifact {ref}",
    "release_error.not_a_draft": "artifact {ref} is a {kind}, not a release_draft",
    "release_error.malformed": "release draft {ref} is malformed: {detail}",
    "release_error.approval_mismatch": "approval does not match the draft package hash",
    "release_error.package_mismatch": (
        "draft spec and scenarios do not match the recorded package hash"
    ),
    "release_error.spec_mismatch": "draft spec does not match its recorded hash",
    "release_error.not_clean": "draft is not clean on re-check: {where}",
    "release_error.would_drop": "draft scenarios carry values the sanitizer would drop",
    "release.draft_for_review": "Draft for approval: {path}",
    "release.package_sha": "Package SHA-256 (spec + scenarios): {sha}",
    "release.body_warning_note": (
        "Request-body strings match the original's code or text. The scenario sends them as "
        "is: check that they are data, not the original's expression."
    ),
    "finding.code": "code",
    "finding.verbatim": "verbatim text",
    "finding.brand": "brand",
    "finding.url": "domain",
    "finding.body_warning": "warning (request body)",
    # Spec markdown
    "spec_md.title": "{product} — behavioral spec v{version}",
    "spec_md.overview": "Overview",
    "spec_md.features": "Features",
    "spec_md.entities": "Entities",
    "spec_md.rules": "Rules",
    "spec_md.api": "API",
    "spec_md.gaps": "Gaps",
    "spec_md.confidence": "confidence: {confidence}",
    "spec_md.request": "request",
    "spec_md.response": "response {status}",
    # Release draft markdown (what the approver reads)
    "release_md.scenarios": "Scenarios",
    "release_md.critical": "critical",
    "release_md.body": "body",
    "release_md.status": "status {status}",
    "release_md.shape": "shape",
    "release_md.save": "save",
    "release_md.withheld": "Withheld expected values",
    "release_md.withheld_row": "{scenario}, step {step}: `{pointer}`",
    "release_md.warnings": "Warnings",
    "release_md.report": "Sanitizer report",
    "release_md.package_sha": "Package SHA-256 (spec + scenarios): `{sha}`",
    "release_md.spec_sha": "Spec SHA-256: `{sha}`",
    "release_md.scenario_count": "Scenarios: {count}",
    # Build, parity and audit lines (CLI output and console job logs)
    "build.local_sandbox_warning": (
        "Warning: LocalSandbox does not isolate the clone's code from this machine."
    ),
    "build.parity_line": (
        "Parity: {passed}/{total} ({ratio:.2%}), critical: {critical_passed}/{critical_total} "
        "({critical_ratio:.2%}), unstable: {unstable}"
    ),
    "build.skipped_unsafe": "Write scenarios skipped (target is not a sandbox): {count}",
    "build.withheld_mismatches": "Mismatches on withheld values: {count}",
    "build.workdir": "Clone working directory: {path}",
    "build.threshold_met": "Threshold met.",
    "build.threshold_missed": "Threshold missed.",
    "audit.pack": "Evidence pack: {path}",
    "audit.similarity": "Max code similarity: {score:.4f} (threshold {threshold})",
    "audit.brand_hits": "Brand mentions in code: {count}",
    "audit.failed": "Audit failed.",
    # Evidence pack README
    "evidence.title": "Evidence pack: {product}",
    "evidence.ledger": "Ledger integrity",
    "evidence.ledger_ok": "Status: intact (hash chain verified)",
    "evidence.ledger_broken": "Status: BROKEN",
    "evidence.ledger_count": "Ledger entries: {count}",
    "evidence.ledger_first_broken": "First broken entry: {line} ({reason})",
    "evidence.approvals": "Approvals",
    "evidence.approval": (
        "{approver} ({role}), {approved_at}, package sha256 (spec + scenarios): {sha}"
    ),
    "evidence.no_approvals": "No approved releases.",
    "evidence.parity": "Parity",
    "evidence.parity_ratio": "Share of scenarios passed: {ratio:.3f}",
    "evidence.parity_critical": "Share of critical scenarios passed: {ratio:.3f}",
    "evidence.parity_total": "Total scenarios: {count}",
    "evidence.parity_unstable": "Unstable scenarios: {count}",
    "evidence.parity_skipped": "Write scenarios skipped (target is not a sandbox): {count}",
    "evidence.parity_withheld": "Mismatches on withheld values: {count}",
    "evidence.similarity": "Code similarity",
    "evidence.similarity_max": "Max similarity: {score:.4f} against a threshold of {threshold}",
    "evidence.similarity_below": "Similarity below threshold: {answer}",
    "evidence.brand": "Brand mentions",
    "evidence.brand_none": "No mentions found.",
    "evidence.sandbox": "Implementation sandbox",
    "evidence.sandbox_never": "Implementation never ran.",
    "evidence.sandbox_isolated": "Sandbox: isolated",
    "evidence.sandbox_not_isolated": (
        "Sandbox: not isolated (LocalSandbox: the clone's code ran on the operator's machine "
        "without file system or network isolation)"
    ),
    "evidence.risks": "Intake risks",
    "evidence.risks_none": "None.",
    "evidence.models": "Models",
    "evidence.model_row": {
        "one": "{model} ({provider}): {count} call, cost ${cost:.4f}",
        "other": "{model} ({provider}): {count} calls, cost ${cost:.4f}",
    },
    "evidence.models_none": "No LLM calls.",
    "evidence.disclaimer": "This document is not a legal opinion.",
    # CLI
    "cli.error": "Error: {message}",
    "cli.environment_error": "Environment error: {message}",
    "cli.project_not_found": "project not found: {path}",
    "cli.card_not_found": "card file not found: {path}",
    "cli.bad_lang": "unsupported language “{value}”: use {choices} (or set {env})",
    "cli.init.created": "Project created: {path}",
    "cli.init.flags": "Risk flags: {flags}",
    "cli.prepare_release.next": (
        "To release: reverseai approve --project {project} --approver <NAME> "
        "--role <operator|customer_analyst> --sha {sha}"
    ),
    "cli.approve.released": "Release approved: {ref}",
    "cli.build.unstable_refused": (
        "the released scenarios change the target's data, and the CLI cannot reset it "
        "between scenarios: parity results will be unstable. Run with --allow-unstable "
        "to continue."
    ),
    "cli.ledger.ok": "Ledger intact: hash chain unbroken, events: {count}",
    "cli.ledger.broken": "Ledger integrity broken: line {line} ({reason})",
    "cli.costs.calls": "LLM calls: {count}",
    "cli.costs.total": "Cost, USD: {total:.4f}",
    "cli.costs.by_role": "By role:",
    "cli.costs.by_model": "By model:",
    "cli.costs.row": {
        "one": "  {key}: {count} call, {cost:.4f} USD",
        "other": "  {key}: {count} calls, {cost:.4f} USD",
    },
    "cli.status.project": "Project: {name} ({path})",
    "cli.status.completed": "Completed phases:",
    "cli.status.artifacts": "Artifacts:",
    "cli.status.no_artifacts": "Artifacts: none",
    "cli.status.rounds": "Parity rounds: {count}",
    "cli.bench.offline": (
        "The offline benchmark (a scripted model instead of an LLM) runs only in tests: "
        "uv run pytest tests/e2e. For a run with real models, pass --live."
    ),
    "cli.bench.target": "Benchmark: {target}",
    "cli.bench.scenarios": "Scenarios: {count}",
    "cli.bench.parity": "Parity: {ratio:.2%}, critical: {critical:.2%}",
    "cli.bench.hidden": "Hidden tests: {passed}/{total}",
    "cli.bench.similarity": "Max code similarity: {score:.4f}",
    "cli.bench.duration": "Duration, s: {seconds:.1f}",
    "cli.bench.result": "Result: {path}",
    "cli.console.token_required": (
        "address {host} is reachable beyond this machine: set an access token in the {env} "
        "environment variable or run the console on 127.0.0.1"
    ),
    "cli.console.url": "ReverseAI console: {url}",
    "cli.console.login": "Sign in: {url}/login (the token is the value of {env})",
    "cli.console.stop": "Stop: Ctrl+C",
    "cli.help.app": "ReverseAI: a clean-room pipeline for web applications.",
    "cli.help.lang": "Interface language: en or ru (default: REVERSEAI_LANG, else en).",
    "cli.help.project": "Project directory.",
    "cli.help.init": "Create a project from a card (legal intake check).",
    "cli.help.card": "Project card (YAML).",
    "cli.help.projects_root_init": "Directory to create the project in.",
    "cli.help.observe": "Observe: crawl the target in a browser and, on a sandbox, probe its API.",
    "cli.help.oracle": "Build executable behavior scenarios.",
    "cli.help.spec": "Write the behavioral spec (analyst + critic).",
    "cli.help.prepare_release": "Sanitize the spec and prepare the draft for approval.",
    "cli.help.approve": "Approve the draft and release it into the clean zone.",
    "cli.help.approver": "Who approves.",
    "cli.help.role": "operator (platform operator) or customer_analyst (customer analyst).",
    "cli.help.sha": "SHA-256 of the package being approved (spec + scenarios).",
    "cli.help.build": (
        "Implement in the clean zone and check parity (exit code 2 if the threshold is missed)."
    ),
    "cli.help.allow_unstable": (
        "Run even though the scenarios change sandbox data and nothing resets it between them."
    ),
    "cli.help.audit": (
        "Code similarity audit and evidence pack (exit code 2 if the audit fails)."
    ),
    "cli.help.out": "Directory for the evidence pack.",
    "cli.help.ledger_verify": "Verify the integrity of the provenance ledger.",
    "cli.help.costs": "LLM cost summary from the ledger.",
    "cli.help.status": "Show completed phases and artifact references.",
    "cli.help.bench": "Run the whole pipeline on a reference target and compute metrics.",
    "cli.help.target": "Reference target (bench/targets).",
    "cli.help.live": "Real models, keys from environment variables.",
    "cli.help.workdir": "Run directory.",
    "cli.help.console": (
        "Web console: projects, phases, release approval, parity and the evidence pack."
    ),
    "cli.help.projects_root": "Directory with projects.",
    "cli.help.host": "Server address (default: this machine only).",
    "cli.help.operator": "Operator name: initials in the header, default signer.",
    "cli.help.console_lang": (
        "Default console language: en or ru (each viewer can switch in the header)."
    ),
    # Console: shared services
    "console.no_provider_key": (
        "no LLM provider key is set: set an environment variable ({names}) and restart "
        "the console"
    ),
    "console.operator_initials": "OP",
    "console.build_label": "Build and parity",
    "console.prepare_release.next": "To release, approve the package on the Release page.",
    "console.build.unstable_refused": (
        "the released scenarios change the target's data, and the console cannot reset it "
        "between scenarios: parity results will be unstable. Tick “Allow an unstable run” "
        "to continue."
    ),
    "console.already_released": (
        "the package is already released. To release a new one, rerun release preparation."
    ),
    "console.draft_changed": "the draft has changed — reload the page and review the package again",
    "registry.unreadable_file": "file cannot be read ({error})",
    "registry.bad_card": "card is damaged: {problem}",
    "registry.bad_state": "pipeline state is damaged: {problem}",
    "role.operator": "Platform operator",
    "role.customer_analyst": "Customer analyst",
    "role.recorded.operator": "platform operator",
    "role.recorded.customer_analyst": "customer analyst",
    "role.recorded.customer_lawyer": "customer lawyer (before D-010)",
    "mode.legacy": "LEGACY",
    "mode.import_substitution": "IMPORT SUBSTITUTION",
    "mode_option.legacy": "Legacy (system replacement)",
    "mode_option.import_substitution": "Import substitution",
    "jurisdiction.us": "US",
    "jurisdiction.eu": "EU",
    "jurisdiction.cn": "China",
    "jurisdiction.self": "Self-hosted",
    "evidence_file.README": "summary",
    "evidence_file.ledger": "ledger",
    "evidence_file.ledger_verification": "integrity",
    "evidence_file.release": "signed package",
    "evidence_file.sanitize_report": "sanitization",
    "evidence_file.parity_report": "parity",
    "evidence_file.similarity_report": "similarity",
    "evidence_file.models_used": "models",
    "evidence_file.zones_access": "zone access",
    "evidence_outside": (
        "The pack was built outside the console (reverseai audit --out …), so it is not here. "
        "To download it from the console, rerun the audit on the project page."
    ),
    # Console: forms and actions
    "form.name_required": "Enter a project name.",
    "form.unknown_mode": "Unknown project mode.",
    "form.url_required": "Enter the target URL.",
    "form.domains_required": "Enter at least one allowed domain.",
    "form.product_required": "Enter the clone's product name.",
    "form.jurisdiction_required": "Select at least one jurisdiction.",
    "form.invalid_card": "Invalid card data: {summary}.",
    "form.intake.attestation_required": "Confirm lawful access to the target.",
    "form.intake.host_not_allowed": "Target host “{host}” is not among the allowed domains.",
    "form.intake.product_reuses_brand": "Product name “{name}” repeats the original's brand.",
    "form.intake.project_exists": "A project with this name already exists.",
    "form.intake.no_usable_characters": "The project name has no letters or digits.",
    "phases.busy": "A job is already running for this project: “{label}”. Wait for it to finish.",
    "phases.bad_max_pages": "Page count must be a whole number of 1 or more.",
    "phases.bad_max_rounds": "Round count must be a whole number of 1 or more.",
    "approve.approver_required": "Enter who approves the package.",
    "approve.unknown_role": "Unknown approver role.",
    "approve.confirm_required": "Confirm that you reviewed the package: tick the checkbox.",
    "approve.wait_job": "Wait for the job “{label}” to finish.",
    "job_status.running": "running",
    "job_status.succeeded": "done",
    "job_status.attention": "needs attention",
    "job_status.failed": "failed",
    "job.internal_error": "Internal error ({error}). See the server log for details.",
    # Console: error pages
    "errors.internal.title": "Internal error",
    "errors.internal.message": "The request failed ({error}). See the server log for details.",
    "errors.project_not_found.title": "Project not found",
    "errors.project_not_found.message": "There is no project with this name in the projects directory.",
    "errors.project_invalid.title": "Project is damaged",
    "errors.project_invalid.message": "Project “{name}” cannot be opened: {reason}.",
    "errors.bad_request.title": "Bad request",
    "errors.bad_request.message": "The request parameters failed validation.",
    "errors.bad_request.fields": "Fields: {fields}.",
    "errors.csrf.title": "Form expired",
    "errors.csrf.message": "The form token is invalid. Reload the page and try again.",
    "errors.not_found.title": "Page not found",
    "errors.not_found.message": "This page does not exist.",
    "errors.http.title": "Request error",
    "errors.no_evidence.title": "No evidence pack",
    "errors.no_action.title": "Action not found",
    "errors.no_action.message": "No such phase: “{action}”.",
    "error_page.eyebrow": "ERROR",
    "error_page.back": "ALL PROJECTS",
    # Console: header
    "nav.label": "Sections",
    "nav.projects": "PROJECTS",
    "nav.overview": "OVERVIEW",
    "nav.release": "RELEASE",
    "nav.parity": "PARITY",
    "nav.costs": "COSTS",
    "nav.ledger": "LEDGER",
    "nav.language": "Language",
    "nav.theme": "Toggle theme",
    "nav.operator": "Operator",
    # Console: login
    "login.page_title": "Sign in",
    "login.eyebrow": "ACCESS",
    "login.title": "Access token required",
    "login.message": (
        "This console is reachable beyond this machine. Enter the access token or send an "
        "Authorization: Bearer header."
    ),
    "login.token_label": "Access token (value of REVERSEAI_CONSOLE_TOKEN)",
    "login.submit": "SIGN IN",
    "login.wrong_token": "Wrong access token.",
    # Console: projects list
    "projects.page_title": "Projects",
    "projects.eyebrow": "DIRECTORY",
    "projects.title": "PROJECTS",
    "projects.lede": (
        "Every project moves through nine phases: from intake and observing the target to "
        "releasing the package through the barrier, implementation, parity and audit."
    ),
    "projects.new": "NEW PROJECT",
    "projects.all": "ALL PROJECTS",
    "projects.col.project": "PROJECT",
    "projects.col.mode": "MODE",
    "projects.col.target": "TARGET",
    "projects.col.phases": "PHASES",
    "projects.col.activity": "ACTIVITY",
    "projects.broken": "The project cannot be opened: fix the files in its directory.",
    "projects.clone": "clone: {product}",
    "projects.sandbox": "sandbox",
    "projects.progress": "Phases complete: {done} of 9",
    "projects.empty": (
        "No projects yet. Create the first one: a project card, an attestation of lawful "
        "access and the allowed domains."
    ),
    # Console: new project
    "new.page_title": "New project",
    "new.eyebrow": "PHASE 01 · INTAKE",
    "new.title": "NEW PROJECT",
    "new.lede": (
        "The project card passes the legal intake check: lawful access to the target, the "
        "target host among the allowed domains, a clone name free of the original's brand."
    ),
    "new.section.project": "PROJECT",
    "new.section.target": "TARGET",
    "new.section.policy": "DATA POLICY",
    "new.section.attestation": "ATTESTATION",
    "new.name": "Project name",
    "new.mode": "Mode",
    "new.product": "Clone product name",
    "new.product_hint": "Must not repeat the original's brand.",
    "new.brand": "Original's brand",
    "new.brand_hint": (
        "Comma- or newline-separated. Cut from everything that crosses the barrier."
    ),
    "new.url": "Target URL",
    "new.domains": "Allowed domains",
    "new.domains_hint": "The target host must be on the list. Comma- or newline-separated.",
    "new.sandbox": (
        "The target is a sandbox: form submission, API probing and write scenarios are allowed."
    ),
    "new.jurisdictions_label": "Model provider jurisdictions",
    "new.jurisdictions_hint": "Models are called only from providers in the selected jurisdictions.",
    "new.jurisdiction": "Project jurisdiction",
    "new.basis": "Basis of access",
    "new.basis_placeholder": "Contract, license, own system",
    "new.signed_by": "Signed by",
    "new.signed_at": "Signed at",
    "new.signed_at_hint": "ISO 8601. Leave empty for now.",
    "new.lawful_access": (
        "I confirm lawful access to the target and the right to study its behavior."
    ),
    "new.submit": "CREATE PROJECT",
    "new.cancel": "CANCEL",
    # Console: project overview
    "overview.eyebrow": "PROJECT {name}",
    "overview.sandbox": "SANDBOX",
    "overview.read_only": "READ ONLY",
    "overview.lede_intact": (
        "An independent reimplementation of the target from its observable behavior. "
        "{count} of 9 phases complete; the provenance ledger is intact."
    ),
    "overview.lede_broken": (
        "An independent reimplementation of the target from its observable behavior. "
        "{count} of 9 phases complete; the provenance ledger is damaged."
    ),
    "overview.release": "RELEASE",
    "overview.evidence": "EVIDENCE PACK",
    "overview.track": "TIMELINE",
    "overview.stage.done": "Complete",
    "overview.stage.awaiting_approval": "Awaiting approval",
    "overview.stage.ready": "Ready to run",
    "overview.stage.waiting": "Waiting",
    "overview.kpis": "Key metrics",
    "overview.zones": "ZONES",
    "overview.zones_note": (
        "The clean zone reads only the released package. Any attempt to read the dirty zone "
        "is blocked and logged."
    ),
    "overview.ledger": "PROVENANCE LEDGER",
    "overview.integrity_ok": {
        "one": "{count} event · chain intact",
        "other": "{count} events · chain intact",
    },
    "overview.integrity_broken": "Integrity broken: entry {line} ({reason})",
    "overview.filter": "Event type starts with",
    "overview.filter_submit": "SHOW",
    "overview.filter_all": "all",
    "overview.hide_artifacts": "hide artifacts",
    "overview.show_artifacts": "show artifacts",
    "overview.col.time": "TIME",
    "overview.col.event": "EVENT",
    "overview.col.summary": "SUMMARY",
    "overview.col.zone": "ZONE",
    "overview.col.actor": "ACTOR",
    "overview.col.hash": "HASH",
    "overview.no_events": "No events of this type.",
    "overview.shown": "Showing the latest {shown} of {total}.",
    "overview.show_all": "Show all",
    "overview.hidden_artifacts": "Hidden artifact.* events: {count} (artifact writes and reads).",
    "detail.intake": "Access attested; risks: {flags}",
    "detail.no_risks": "none found",
    "detail.pages": {"one": "{count} page", "other": "{count} pages"},
    "detail.exchanges": {"one": "{count} exchange", "other": "{count} exchanges"},
    "detail.probes": {"one": "{count} API probe", "other": "{count} API probes"},
    "detail.scenarios": {"one": "{count} scenario", "other": "{count} scenarios"},
    "detail.dropped": "dropped: {count}",
    "detail.features": {"one": "{count} feature", "other": "{count} features"},
    "detail.rules": {"one": "{count} rule", "other": "{count} rules"},
    "detail.findings": "Sanitizer findings: {count}",
    "detail.signed": "Package {sha}… signed",
    "detail.iterations": {"one": "{count} iteration", "other": "{count} iterations"},
    "detail.parity": {"one": "{ratio:.3f} in {count} round", "other": "{ratio:.3f} in {count} rounds"},
    "detail.audit_outside": "Pack built outside the console",
    "detail.similarity": "Similarity {score:.3f}",
    "kpi.parity": "PARITY",
    "kpi.critical": "CRITICAL",
    "kpi.similarity": "CODE SIMILARITY",
    "kpi.scenarios_passed": {
        "one": "{passed} of {count} scenario",
        "other": "{passed} of {count} scenarios",
    },
    "kpi.no_report": "No report",
    "kpi.threshold": "threshold {threshold:.3f}",
    "kpi.audit_outside": "Audited outside the console",
    "kpi.no_audit": "Not audited yet",
    "kpi.calls": {"one": "{count} call", "other": "{count} calls"},
    "summary.phase": "phase {phase}",
    "summary.invalidated": "invalidated: {phases}",
    # Console: job panel and phase controls
    "job.title": "JOB",
    "job.started": "started {time}",
    "job.finished": "finished {time}",
    "job.none": (
        "No jobs in this console session yet. Start phases with the buttons below; one job "
        "runs per project at a time."
    ),
    "run.title": "RUN PHASES",
    "run.invalidates": "Rerunning a phase resets every later phase.",
    "run.done": "done",
    "run.rerun": "RERUN",
    "run.start": "RUN",
    "run.observe.title": "OBSERVE",
    "run.observe.note": "Browser crawl of the target; on a sandbox, forms and API probing too.",
    "run.max_pages": "Max pages",
    "run.submit_forms": "Submit forms",
    "run.probe": "Probe the API",
    "run.read_only": "The target is not a sandbox: read only.",
    "run.oracle.title": "ORACLE",
    "run.oracle.note": "Executable behavior scenarios from the observed exchanges.",
    "run.spec.title": "SPEC",
    "run.spec.note": "An analyst and a critic write the behavioral spec (LLM calls).",
    "run.prepare.title": "PREPARE RELEASE",
    "run.prepare.note": (
        "The sanitizer cleans the spec and scenarios; the draft waits for approval."
    ),
    "run.build.title": "BUILD AND PARITY",
    "run.build.note": (
        "Agents write the clone in the clean zone; parity compares it with the original."
    ),
    "run.max_rounds": "Max rounds",
    "run.allow_unstable": "Allow an unstable run",
    "run.local_sandbox": "LocalSandbox does not isolate the clone's code from this machine.",
    "run.audit.title": "AUDIT",
    "run.audit.note": "Code similarity, brand mentions and the evidence pack.",
    # Console: costs
    "costs.page_title": "Costs · {name}",
    "costs.eyebrow": "LEDGER",
    "costs.title": "COSTS",
    "costs.lede_before": (
        "Every model call goes through the gateway and is recorded in the provenance ledger. "
        "Totals match"
    ),
    "costs.lede_after": ".",
    "costs.totals": "Totals",
    "costs.calls": "LLM CALLS",
    "costs.calls_sub": "from the project ledger",
    "costs.cost": "COST",
    "costs.cost_sub": "USD at configured prices",
    "costs.by_role": "BY ROLE",
    "costs.by_model": "BY MODEL",
    "costs.col.role": "ROLE",
    "costs.col.model": "MODEL (PROVIDER)",
    "costs.col.calls": "CALLS",
    "costs.none": "No LLM calls yet.",
    # Console: parity and evidence
    "parity_page.page_title": "Parity · {name}",
    "parity_page.eyebrow": "PHASES 08–09",
    "parity_page.title": "PARITY",
    "parity_page.lede": (
        "The same scenarios run on the original and on the clone. They are compared on "
        "behavior and data, not on appearance."
    ),
    "parity_page.met": "THRESHOLD MET",
    "parity_page.missed": "THRESHOLD MISSED",
    "parity_page.none_before": "Parity has not been checked yet. Run “Build and parity” on the",
    "parity_page.none_link": "project page",
    "parity_page.none_after": "once the package is released.",
    "parity_page.totals": "Totals",
    "parity_page.threshold": "threshold {threshold:.2f}",
    "parity_page.unstable": "UNSTABLE",
    "parity_page.unstable_sub": "at most {limit}%, none critical",
    "parity_page.rounds": "ROUNDS",
    "parity_page.rounds_sub": "build → parity",
    "parity_page.scenarios": "SCENARIOS",
    "parity_page.col.scenario": "SCENARIO",
    "parity_page.col.original": "ORIGINAL",
    "parity_page.col.clone": "CLONE",
    "parity_page.col.failures": "MISMATCHES",
    "parity_page.unstable_short": "UNSTABLE",
    "parity_page.skipped": "write scenarios skipped (target is not a sandbox): {count}",
    "parity_page.unstable_on_original": "unstable on the original: {ids}",
    "parity_page.allowed": "of {threshold:.3f} allowed",
    "parity_page.meter": "Similarity {score:.3f} against a threshold of {threshold:.3f}",
    "parity_page.similarity_note": (
        "Share of the clone's code fragments that match the original's code (JS/CSS), "
        "8-token window."
    ),
    "parity_page.brand_hits": "BRAND MENTIONS",
    "parity_page.no_brand_hits": "No brand mentions found.",
    "parity_page.audit_outside": (
        "Audited outside the console: its similarity report is in the evidence pack built by"
    ),
    "parity_page.no_audit": "Not audited yet.",
    "parity_page.download": "DOWNLOAD",
    "parity_page.evidence_missing": "The evidence pack has not been built yet: run the audit.",
    "parity_page.not_isolated": (
        "The implementation sandbox is not isolated (LocalSandbox): the clone's code ran on "
        "the operator's machine. The pack says so explicitly."
    ),
    "parity_page.handoff": (
        "The pack goes to the customer's lawyer. This document is not a legal opinion."
    ),
    "scenario.critical": "critical",
    "scenario.regular": "regular",
    "scenario.step": "step {step}",
    # Console: release review
    "release_page.page_title": "Release · {name}",
    "release_page.eyebrow": "PHASE 06 · BARRIER",
    "release_page.title": "PACKAGE v{version}",
    "release_page.lede": (
        "Everything the implementing agents will see: the spec and scenarios after "
        "sanitization. The signature is bound to the package hash — once signed, the content "
        "cannot change."
    ),
    "release_page.no_draft_before": (
        "The release draft is not ready yet. Run “Release preparation” on the"
    ),
    "release_page.no_draft_after": ".",
    "release_page.contents": "Package contents",
    "release_page.tab.spec": "SPEC",
    "release_page.tab.scenarios": "SCENARIOS",
    "release_page.tab.cleanup": "SANITIZATION",
    "release_page.features": "FEATURES",
    "release_page.rules": "RULES",
    "release_page.entities": "ENTITIES",
    "release_page.gaps": "GAPS",
    "release_page.col.steps": "REQUESTS AND EXPECTATIONS",
    "release_page.col.type": "TYPE",
    "release_page.no_scenarios": "No scenarios.",
    "release_page.findings": "FINDINGS",
    "release_page.warnings": "WARNINGS",
    "release_page.withheld": "WITHHELD",
    "release_page.dropped": "DROPPED BY ORACLE",
    "release_page.sanitizer_note": (
        "The sanitizer checks every text in the package against the original's vocabulary: "
        "code, pages, server responses. Matches of 8 or more words, the brand and domains are "
        "cut; long and prose-like expected values are withheld."
    ),
    "release_page.sanitizer_findings": "SANITIZER FINDINGS",
    "release_page.no_findings": "The sanitizer found nothing.",
    "release_page.warnings_note": (
        "Request-body strings match the original's code or text. The scenario sends them as "
        "is and they do not block the release: check that they are data, not the original's "
        "expression."
    ),
    "release_page.withheld_title": "WITHHELD EXPECTED VALUES",
    "release_page.nothing_withheld": "Nothing withheld.",
    "release_page.not_replayed": "Scenarios were not replayed on a reset original.",
    "release_page.not_reproduced": "does not reproduce on a clean original",
    "release_page.nothing_dropped": "Nothing dropped.",
    "release_page.signature": "Signature",
    "release_page.signature_title": "PACKAGE SIGNATURE",
    "release_page.package_sha": "Package SHA-256 (spec + scenarios)",
    "release_page.readable_draft": "Readable draft",
    "release_page.released": "RELEASED",
    "release_page.released_note": (
        "The package is in the clean zone. The barrier.approved and barrier.release events "
        "are in the ledger."
    ),
    "release_page.to_parity": "TO PARITY",
    "release_page.approver": "Approver",
    "release_page.role": "Role",
    "release_page.confirm": (
        "I reviewed the package: it contains no code, text or brand of the original."
    ),
    "release_page.submit": "APPROVE AND RELEASE",
    "release_page.lawyer_note": (
        "The customer's lawyer receives the final evidence pack after the audit."
    ),
}
