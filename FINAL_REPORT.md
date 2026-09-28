# CAMPUS implementation and validation checkpoint

Status: continuation in progress. This file is a recoverable checkpoint, not a declaration that all master requirements are complete.

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

## Provider status at recovery

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

## Remaining high-value work

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
