# CAMPUS implementation and validation checkpoint

Status: working initial release with real read-only integrations; broader product requirements remain PARTIAL. Continuation validation date: 2026-09-28. The original implementation was preserved and extended, not replaced.

## Current outcome

### Policy-semantics continuation (validated implementation)

Renewed expired Portal/Moodle sessions through the existing credential flow. Moodle now persists visible resource metadata, announcement-index titles (without opening threads), and teaching-plan/presentation PDF text linked to courses. Five real policy documents were inspected. Three yield usable component formulas with unresolved approval rules, one exposes a formula/weight conflict, and one contains a summation/weight ambiguity. No apparent typo or grade-scale inconsistency was silently corrected. Deterministic bounded AST algebra (no eval), versioned policy evidence, automatic grade questions and explicit `grade-policy` scenarios are implemented; real recorded component matching remains incomplete. Current grade calculations must not imply approval.

Portal now extracts explicit A/B/C/D/E workload balances, distinguishes approved from curriculum-validated hours, preserves individual equivalency credit decisions, and models the explicit absence formula as an attendance policy. Elective-group and extension-hour balances retain their distinct source semantics. The planner exposes those requirements without claiming a graduation date. Real synchronization now contains structured requirements and individual equivalency decisions; unchanged repeat Portal and Moodle syncs each produced zero new value changes.

The final suite is **101 passing tests**, both from source and against the installed release wheel. Ruff lint and formatting pass. The wheel and source distribution built successfully; archive audits found no loaded credentials or private-state paths (31 wheel files, 65 source-distribution files at audit). Repository audit checks both 64 publishable worktree files and their actual Git index blobs, plus private report/log text, without exposing matches. No private academic data became fixtures. `doctor` verified Portal/Moodle/Gmail authentication and database health; optional GitHub remains BLOCKED without `gh`.

New commands exercised against real state: `analyze-policies`, `grade-policy`, `requirements`, `announcements`, `events`, `grades`, and Portuguese grade questions. Existing status/deadline/attendance/planner/evidence/work/report commands also run. Work generates validated preparation files and structured format/naming requirements, but remains PARTIAL: checklists are never counted as requested academic deliverables. Candidate events preserve separate mail/forum evidence and do not overwrite deadlines. Hypothetical arithmetic works using three real extracted formulas without manually supplying weights; **a reliable actual required-to-pass answer is still blocked** by missing component-grade matches, absent policy details or genuine source inconsistencies. No passing threshold was guessed.

Recovery substitution is deterministic when a source supplies one unambiguous rule. Conflicting replacement targets are blocked, as are unknown target grades and unequal-weight tie cases. Ordinary formula evaluation is separate from recovery eligibility or approval. Policy revisions use stable resource identity and preserve old evidence/history rather than accumulating obsolete current formulas as independent authorities.

Feedback discovery inspected three already-submitted assignment views; no feedback section appeared in that sample. Announcement coverage is index titles only; discussion bodies are intentionally not opened because that may update read tracking. Remaining high-value work requires either additional explicit source semantics or a reviewed source path: resolve ambiguous passing/recovery rules with authoritative clarification, establish exact grade-component mappings as marks become available, inspect further feedback/announcement-body access without unwanted state changes, and extend deliverable-content validation beyond file presence.

- Python 3.12+ / Typer / Rich / SQLite / Playwright. Python was retained for its mature browser, SQLite and document libraries and deterministic calculation support. See ADR 001.
- Portal academic synchronization is now REAL-VALIDATED: enrollment, attendance policy/periods, regular timetable, assessments, history, missing-course requirements and curriculum. The previous academic-extraction blocker is resolved.
- Moodle browser synchronization and same-origin PDF attachment download/extraction are REAL-VALIDATED. Exact code/semester/section matching now correlates Portal and Moodle courses persistently.
- Gmail academic snippets are REAL-VALIDATED. Deterministic topic/date mentions and course candidates now carry source evidence; ambiguous email snippets never overwrite confirmed deadlines.
- Repeated real Portal, Moodle and Gmail synchronization each produced **zero** duplicate value changes for unchanged source data.
- Regular-weekday attendance scenarios work through both `attendance --day friday` and `ask "can I miss Friday?"`. The result preserves stale-data warnings and unknown calendar exceptions; no blanket permission to miss class is given.
- Curriculum planning uses the real known mandatory subset, explicit completion and prerequisite data; unresolved period gates, electives and non-course requirements remain visible. A graduation date is UNKNOWN, not invented.
- Work preparation now includes linked extracted attachment instructions and evidence IDs, flags unread attachments, detects unsupported Packet Tracer work and includes repository/commit provenance when explicitly linked. This remains preparation, not assignment completion.
- ZIP packages contain per-file hashes; standalone artifacts have sidecar manifests. MD/TXT/PDF/DOCX/ZIP validation and reproducibility are tested. The unread-change count no longer truncates at the display page size.
- Gmail IMAP MIME decoding now respects the message's charset and transfer encoding. This path is synthetic-tested, not live-validated.

## Current provider validation

| Provider | Current evidence |
| --- | --- |
| Portal | REAL-VALIDATED / PARTIAL coverage. Live authentication HEALTHY; academic facts persisted. |
| Moodle browser | REAL-VALIDATED / PARTIAL coverage. Live authentication HEALTHY; courses, assignments, deadlines, submission states, attachments. |
| Gmail browser | REAL-VALIDATED / PARTIAL coverage. Live institutional authentication HEALTHY; first-page academic snippets and local candidate analysis. |
| Local Git | REAL-VALIDATED. Configured project discovery and read-only metadata. |
| Moodle token API | IMPLEMENTED; method boundary tested; no existing token available for real validation. |
| Gmail IMAP | IMPLEMENTED / parser-tested; no institution-authorized app password available for real validation. |
| GitHub | IMPLEMENTED / BLOCKED because optional `gh` is not installed. |

`doctor` verified Portal, Moodle and Gmail authenticated, Git healthy, and SQLite quick-check HEALTHY. Authentication health does not imply complete academic coverage. Live details remain solely in gitignored private state.

## Validation checkpoint

- Full synthetic suite: **101 passed**. Coverage includes the previous 63 tests plus safe formula algebra, nested averages/sums, explicit percentages, missing/conflicting policies, recovery replacement, stable document revision history, automatic grade questions, workload/elective/extension requirements, individual equivalencies, forum indexes, event provenance and deliverable validation.
- Ruff lint and formatting checks pass. `git diff --check` passes.
- Wheel and source distribution build successfully. Distribution audit found no loaded credentials or private state paths. The built wheel was installed in the project virtual environment to verify the production entry point rather than relying solely on editable imports.
- Representative local commands exercised: status, courses, deadlines, attendance, grades, plan, changes, evidence, analyze-mail, English questions, work and PDF report. Generated files validated; work remained PARTIAL.
- Real read-only checks: Portal/Moodle/Gmail sync, provider doctor, known Moodle PDF downloads. Repository discovery never modified the source project.
- Installed-console `setup --no-authenticate` completed with honest PARTIAL coverage (Portal/Moodle/mail PARTIAL, Git HEALTHY). Installed `doctor` verified the three academic sessions and database HEALTHY. All representative CLI outputs parsed as valid JSON; work generated six validated preparation files and PDF report validation passed. No remote write action was performed.

## Genuine limits and next technical work

### Interrupted-release audit and decision

Recovered the existing 40-file staged checkpoint without resetting or discarding it. The final audit found and fixed several concrete defects: unsupported final formulas must not fall back to intermediate means; independent final formulas and conflicting assessment sources remain CONFLICT; threshold/scale consistency is checked after explicit scale extraction; negated or wrapped recovery prose cannot become an affirmative substitution rule. Synthetic regressions cover each case.

Inspecting actual terminal output also found Moodle assignment titles were being taken from unrelated page headings. The parser now uses the authenticated activity-header structure, with a scoped legacy fallback, rather than global chat/instruction headings. Read-only synchronization corrected all 18 stored assignment titles while preserving history. Status now shows last observed data timestamps even for providers whose coverage is PARTIAL.

**Release decision: retain 0.1.0; do not label this the full intended 1.0.** Daily local evidence, synchronization and conservative academic reasoning are usable. Complete assignment authoring/content verification and complete source coverage are not implemented; missing authoritative grading/eligibility data also prevents reliable approval and graduation answers. These limits are explicit rather than replaced with guessed rules. No speculative rewrite or dependency installation was used to manufacture a release claim.

| Classification | Final scope |
| --- | --- |
| REAL-VALIDATED | Portal/Moodle/Gmail authentication and read synchronization, course correlation, five teaching documents, policy evidence, curriculum balances, corrected assignment titles, local CLI/work/report execution |
| SYNTHETIC-VALIDATED | Supported grade/recovery formulas, automatic scenarios, conflicts, attendance, prerequisite logic, deliverable validation, safe artifact formats, capability denials and parser regressions |
| PARTIAL | Real grading answers without matched components or consistent policy details; mandatory-subset planning; announcement titles/mail snippets; preparation-only work |
| BLOCKED | Optional GitHub without `gh`; live IMAP/token/LLM validation without configured dependencies; actual approval answers without sufficient authoritative evidence |
| INTENTIONALLY UNSUPPORTED | Live remote writes, automatic execution of untrusted assignment commands, arbitrary project/Packet Tracer authoring, treating generated checklists as completed deliverables |
| FUTURE IMPROVEMENT | Further reviewed read-only source coverage, additional explicit policy grammars, full deliverable-content validators, dependency/document/profile hardening |

1. **Academic policies:** course-specific formulas and some recovery rules are extracted, but missing/contradictory passing thresholds, scales and component matches prevent reliable live approval/required-grade answers. Individual credit decisions and explicit workload balances are known; general equivalency rules, period-gate operators and some non-course requirements remain unresolved. A confirmed graduation date is not available.
2. **Source completeness:** Moodle forums/announcements, hidden sections, all feedback and course files are not fully synchronized. Gmail browser mode is snippets/first-page only. Add further parsers only after inspecting actual legitimate read views; full mail content needs an allowed IMAP path or separately reviewed browser behavior that does not mark threads read.
3. **Assignment completion:** no arbitrary project authoring, automatic untrusted build/test execution, Packet Tracer authoring or submission. Work reports correctly retain PARTIAL/BLOCKED. Binary source-package assets require manual review; source ZIPs are not guaranteed complete deliverables.
4. **Interactive authentication:** new/expired sessions may need manual Google/MFA/CAPTCHA/SSO completion. Do not bypass it. The existing sessions worked during final checks, but that is not a guarantee of future session validity.
5. **Optional providers:** live IMAP, Moodle token REST, GitHub and local Ollama semantic responses remain unverified without those configured dependencies. The core CLI has no LLM dependency.
6. **Hardening:** dependency pinning/automated vulnerability updates, isolated hostile-document parsing, profile locking and broader campus-layout fixtures would improve release readiness. Current document bounds are not a full sandbox. There is no automatic removal of externally deleted facts because partial reads cannot prove deletion.

## Security and continuation

No credentials were printed, placed in fixtures/reports or committed. Loaded-secret and private-path audits are part of the checkpoint; auth/session/database/download/report files remain gitignored. No remote submissions, emails, account changes or other academic writes were executed. External content remains non-executable data. Remote-write capabilities are dry-run only, even when confirmation is supplied.

The runtime state is private and unencrypted under repository `.campus` for this development session. Because the workspace is in OneDrive, Git exclusion is **not** cloud-storage exclusion. For ongoing use, choose the default `~/.campus` outside synced folders and authenticate there; do not casually copy live databases or browser profiles.

Resume with `campus --home .campus status` (activate `.venv` first). Inspect [integration findings](docs/integrations.md) before changing provider routes. Recovery baseline was checkpointed as `e3b3962`; later continuation commits preserve these additions. Do not re-discover the campus or replace working providers.

The sections below preserve historical recovery context; where they differ from the current outcome above, they describe the state **before** this continuation.

## Continuation milestone: portal synchronization

Portal academic reads are now REAL-VALIDATED. The adapter follows only the four observed read procedures exposed by authenticated menu cards, decodes their declared ISO-8859-1 HTML, and ignores surrounding identity tables. Live synchronization persisted normalized enrollment, bulletin/attendance, assessment, historical-attempt, missing-course and curriculum facts. The explicit portal absence-limit formula supplies the attendance rule; workload hours are not confused with class periods. Curriculum completion comes from approved/credited history and the explicit missing-course list. Period-based eligibility expressions remain unresolved rather than silently becoming empty prerequisites.

Planner integration now schedules the known mandatory-course subset while listing unresolved prerequisite gates, elective choices and non-course requirements. It never calls that subset a confirmed graduation date. New synthetic tests cover the observed structures and read-procedure boundary; validation is in progress.

## Recovered baseline

- Python 3.12+, Typer/Rich CLI, SQLite versioned facts/evidence/current assertions/change history, isolated providers, deterministic engines, local artifact/report generation, optional local Ollama interface.
- Existing working code was preserved. At continuation start all implementation files were untracked and only the original initialization commit existed; nothing was staged.
- Previous validation: 46 tests passed. Tests cover grades, attendance, prerequisite planning, evidence/conflicts/history, mappings, secret exclusion, deterministic artifacts, capability enforcement, parsers, dotenv and CLI imports.
- Local database confirms real Moodle courses/assignments, institutional Gmail thread snippets, and a local repository. No private academic details are reproduced here.
- Local CLI runs previously exercised status, courses, deadlines, grades, attendance, plan, changes, evidence, questions, work and PDF reports. Work correctly remained PARTIAL.
- No remote writes, submissions, email sends or account-setting changes were performed.

## Provider status at recovery (historical)

| Provider | Implementation / validation |
| --- | --- |
| Portal | PARTIAL. Authentication and Cornélio Procópio menu were REAL-VALIDATED; academic extraction not yet synchronized. Session expired during interruption. |
| Moodle browser | REAL-VALIDATED / PARTIAL. Courses, visible assignments, Portuguese deadlines, descriptions, attachments and submission states. |
| Gmail browser | REAL-VALIDATED / PARTIAL. Institutional identity and first-page academic thread snippets; no thread opening. Classification/correlation needs improvement. |
| Local Git | REAL-VALIDATED. Read-only metadata discovery; no repository changes. |
| Moodle token service | IMPLEMENTED, not live-validated without an existing token. |
| Gmail IMAP | IMPLEMENTED, not live-validated without an institution-authorized app password. |
| GitHub | IMPLEMENTED; optional `gh` availability/authentication unverified. |

## Active portal discovery

- User-confirmed entry: `https://sistemas2.utfpr.edu.br/dpls/sistema/aluno02/mpmenu.inicio`, campus Cornélio Procópio.
- Authenticated application naturally supplied `p_unidadelogado=2`. Preserve discovered parameters rather than construct account IDs.
- Verified authenticated marker: `button#logoutButton`.
- Menu is fetched by POST to `mpmenu.pcAjaxMenu`. This observed read operation is allowlisted; modification endpoints remain blocked.
- Academic content lives in iframe `if_navega`.
- Menu `.card-content` elements contain a literal iframe `src` assignment in their onclick attribute. Parse the URL as data; do not execute arbitrary source JavaScript.
- Read-only entries being inspected: Boletim, Disciplinas Matriculadas, Histórico Completo, Matrizes Curriculares.
- The previous session ended immediately before running the revised `tools/inspect_portal_records.py`, which uses authenticated GETs to those discovered URLs.
- Last previous blocker was automatic approval review failing because the usage window expired, not a finding that the read was unsafe.

## High-value work identified at recovery (historical)

1. Complete and real-validate portal grade/enrollment/history/curriculum parsing.
2. Connect real prerequisite/completion data to planner without inventing unknown rules.
3. Improve email/course correlation and event candidates while retaining evidence/conflicts.
4. Validate attachment downloads and repeat-sync idempotence; improve artifact provenance and work preparation.
5. Re-run tests/lint, build distributions, inspect package contents and Git for secrets, validate installed console entry point.
6. Commit reviewed source changes and update this checkpoint with actual results.

## Known limits and safe operation

Credentials load from a gitignored local `.env` with process precedence and no interpolation. Never display the file or values. Existing private state is under `.campus`; reuse with `python -m campus --home .campus ...`. This workspace is in OneDrive: gitignore does not prevent cloud synchronization. Prefer the default `~/.campus` outside synced folders for ongoing use.

Attendance/grade engines require explicit units/rules. Current data gaps return UNKNOWN. Work prepares checklists and eligible tracked source packages; it does not certify assignment completion. Remote capabilities are dry-run only. PDF/DOCX inputs remain untrusted; no embedded code is executed. Browser profiles must not be used concurrently by multiple operations for the same provider.

## Useful commands

```powershell
.venv/Scripts/python.exe tools/integration_probe.py portal --login
.venv/Scripts/python.exe tools/inspect_portal_records.py
.venv/Scripts/python.exe tools/validate_live.py portal
.venv/Scripts/python.exe tools/validate_live.py doctor
.venv/Scripts/python.exe tools/validate_cli.py
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests tools
.venv/Scripts/python.exe -m build
```

Live tools print counts/structural diagnostics. Never turn actual personal records into fixtures. Windows sandbox access to private browser/report/test directories may require approved escalation; preserve restrictive ACLs.
