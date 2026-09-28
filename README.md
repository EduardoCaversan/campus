# CAMPUS

A local-first academic CLI for UTFPR. SQLite stores academic facts, source evidence, snapshots and change history. The application works without an LLM. There is no graphical dashboard; a browser is used for external sign-in and source access.

This is a working initial release, not a claim of complete university-system coverage. Read-only integration has been validated against the Cornélio Procópio Student Portal (enrollment, attendance, assessments, timetable, history and curriculum), Moodle (courses, assignments and attachments), institutional Gmail search snippets, and local Git. Missing information remains `UNKNOWN`; partial preparation is never reported as assignment completion.

## Install

Version **0.1.0** is a usable, read-only initial release, not the complete 1.0 product vision. See [the validation checkpoint](FINAL_REPORT.md) for verified coverage and release limitations.

Python 3.12+ and Git are required. From this repository:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\Activate.ps1
campus --help
```

On macOS/Linux, use `.venv/bin/python` and `source .venv/bin/activate`. If Windows cannot bootstrap pip in the virtual environment, use the host pip: `python -m pip --python .venv/Scripts/python.exe install -e ".[dev]"`.

Alternatively configure `browser_channel = "msedge"` or `"chrome"` to use an installed browser. Browser profiles are separate from your normal browser profile.

## Setup and authentication

```powershell
campus setup --offline
# Edit ~/.campus/config.toml if using an installed browser or project directories.
campus setup
campus status
campus
```

`setup` initializes storage, checks sessions, opens sign-in for providers needing authentication, then synchronizes them independently. The portal defaults to Cornélio Procópio and selects it when unambiguous. Google sign-in, MFA and CAPTCHA are completed manually. A failed provider does not discard other sources. `setup --no-authenticate` only initializes and synchronizes existing sessions; `setup --offline` does no network access.

Credentials can be placed in a **gitignored `.env` in the current working directory**, or provided as environment variables. CAMPUS uses `python-dotenv`; existing process variables take precedence, interpolation is disabled, parent directories are not searched, and values are never printed. See `.env.example` for variable names. Never paste real values into commands or reports.

```powershell
campus auth portal
campus auth moodle
campus auth mail
campus doctor
campus sync
```

Portal/Moodle credential forms can be filled from their corresponding environment variables. CAPTCHA/MFA/SSO never gets bypassed. The portal's verified academic landing route is remembered after successful authentication. Moodle optionally accepts an **existing** `MOODLE_TOKEN`; no new web-service privileges are requested.

For Gmail, no Google Cloud project is needed. Browser mode reads academic **list snippets only** and does not open threads, which can mark mail read. An existing institution-authorized Gmail app password can optionally enable IMAP; configure `mail_mode = "imap"`, `CAMPUS_MAIL_ADDRESS`, and `CAMPUS_MAIL_APP_PASSWORD`. CAMPUS uses read-only mailbox selection and `BODY.PEEK`. **Do not provide your Google password.** Organization policy may prohibit app passwords.

The development session's synchronized data is under the gitignored repository `.campus`. To reuse it:

```powershell
campus --home .campus status
campus --home .campus
```

For ongoing use, prefer the default `~/.campus` outside OneDrive or other cloud-synced directories. Gitignore does not prevent cloud synchronization. Auth profiles and the database are sensitive, unencrypted local data.

## Commands

Global options precede the command: `campus --home PATH --json status`.

| Command | Behavior |
| --- | --- |
| `campus` | Interactive English/Portuguese question loop; noninteractive invocation prints status |
| `setup [--offline] [--no-authenticate]` | Initialize, authenticate and synchronize independently |
| `auth portal\|moodle\|mail` | Establish and verify a persistent browser session |
| `doctor` | Live authentication/provider checks; never infers authentication from saved files |
| `sync [provider] [--force]` | Read sources; cache recent successful/partial data, preserve failures |
| `status` | Compact local summary; no network calls |
| `courses`, `course IDENTIFIER` | Known courses and conflicting source fields |
| `deadlines [--days 7] [--all]` | Pending deadlines; `--all` includes submitted assignments |
| `grades`, `attendance [--miss N] [--day friday]` | Deterministic calculations; weekday scenarios use recorded class periods, not calendar guarantees |
| `grade-scenario FILE --target 6 --scale 10` | JSON component weights/grades; null means unknown |
| `analyze-policies` | Extract course-specific rules from synchronized teaching documents; preserve ambiguities and evidence |
| `grade-policy IDENTIFIER [--set P1=7] [--component P2] [--recovery 8]` | Deterministic policy-based scenarios; never guesses missing components, scale or passing rules |
| `requirements` | Explicit curriculum workload, elective/extension balances and individual equivalency decisions |
| `announcements`, `events` | Known announcement-index titles and evidence-backed candidate events from mail/forums |
| `attendance-scenario TOTAL ABSENCES MINIMUM --held N --miss N` | Explicit consistent units; MINIMUM is a fraction |
| `plan [--max-load 360] [--start-term 1]` | Estimate from synchronized/imported curriculum; lists unresolved gates/electives separately |
| `changes [--acknowledge] [--limit N]` | Unacknowledged fact changes; acknowledgement is local |
| `evidence IDENTIFIER` | Current and historical evidence, source links, timestamps and snapshots |
| `mail`, `repos` | Known academic messages/repositories |
| `analyze-mail` | Deterministic topic/date mentions and course candidates, with source evidence; does not assert new deadlines |
| `correlate` | Course matches; only exact code/semester/section matches are automatically joined |
| `map-course ALIAS CANONICAL` | Explicitly confirm a local course mapping |
| `link-repo ASSIGNMENT PATH` | Explicitly associate an existing assignment and configured repository |
| `download IDENTIFIER` | Download observed Moodle attachment links; bounded, same-origin, never execute |
| `import-document PATH` | Extract PDF/DOCX/TXT/MD text as untrusted evidence |
| `import PATH` | Import explicit normalized facts from JSON; see [data format](docs/data-format.md) |
| `work [IDENTIFIER]` | Prepare checklists with linked downloaded instructions and source ZIPs; validate files, report blockers |
| `artifact NAME --source PATH` | Generate MD/TXT/PDF/DOCX from a supplied document |
| `artifact NAME.zip --repository PATH` | Package eligible tracked text source; report every exclusion |
| `report [--pdf]` | Latest run report; Markdown is canonical |
| `ask "QUESTION"` | Route supported questions to deterministic local tools |
| `capability SEND_EMAIL` | Inspect dry-run remote capability policy; never sends mail |

Interactive shortcuts: `/status`, `/sync`, `/work`, `/help`, `/exit`. Output is terminal-safe: external strings are not interpreted as Rich markup or terminal commands. `--json` emits JSON with escaped Unicode for Windows pipe compatibility. Operational errors return 1; blocked/partial sync, work, doctor and authentication return 2. Informational queries return 0 even when the answer is `UNKNOWN`; inspect their state fields.

## Configuration

Default: `~/.campus/config.toml`. Override with `CAMPUS_HOME`, `--home`, or `--config`. No secret values belong in TOML.

```toml
timezone = "America/Sao_Paulo"
project_dirs = ['C:\Projects\university']
browser_channel = "msedge"
portal_campus = "Cornélio Procópio"
mail_mode = "browser"
mail_days = 30
max_items = 100
stale_hours = 24
sync_interval_minutes = 15
llm_provider = "none"
# Optional local Ollama server; no academic data is sent to hosted model vendors.
# llm_provider = "ollama"
# llm_model = "a-model-you-have-installed"
# llm_url = "http://localhost:11434"
```

All files live under the chosen data directory: database, private auth profiles, downloads, artifacts, reports, logs, and sanitized failure metadata. The optional semantic provider is read-only, uses selected evidence, has no execution tools, and rejects answers without valid evidence IDs. Supported intent calculations never use an LLM. The provider protocol can be extended; hosted providers are intentionally disabled in this release.

## Actual limitations

- Portal academic parsing is validated for Cornélio Procópio's observed legacy pages only. Explicit table headers and the portal's absence-limit formula supply rules and units. Period-gated prerequisites, equivalencies and non-course requirements remain unresolved where the source is insufficient.
- Moodle browser coverage includes visible assignments/resources, bounded teaching-plan/presentation PDFs and announcement-index titles. Discussion bodies are not opened to avoid changing read tracking. Hidden sections and all feedback are not fully covered. Recognized Portuguese dates use the configured timezone, explicitly recorded as an assumption. Token-based coverage remains unverified without an existing token.
- Gmail browser coverage is the first visible result page, up to the configured limit. It records thread snippets, not full messages or attachments. Its private list-fetch endpoint and DOM can change. IMAP covers bounded recent inbox messages only and has not been live-validated without an app password.
- Attendance requires total/held/absent units and the actual minimum attendance rule. Weekday scenarios use the regular timetable and explicitly leave calendar exceptions unknown. Grades display recorded assessments/partial results, but required future grades still need explicit weights, scale and passing grade. CAMPUS never assumes a university-wide rule from memory.
- Plans are deterministic greedy estimates, not promises of graduation or optimal schedules. Unknown offerings and schedule gaps are disclosed; internships, electives, complementary hours and administrative approvals need explicit modeling.
- Work currently prepares evidence/checklists and eligible source packages. It does not author arbitrary projects, execute untrusted build scripts, operate Packet Tracer, or submit assignments. Generated files do not prove academic completion.
- Teaching-policy formulas use bounded deterministic algebra, never `eval`. Explicit formulas/percentages and recovery substitutions are supported; ambiguous summations, inconsistent scales/thresholds and conflicting recovery instructions remain unresolved. Real documents contain such ambiguities. `grades` and supported Portuguese questions use the extracted policies, but a numeric answer still requires matching component grades. Manual `grade-scenario` remains available.
- Work extracts explicit/candidate deliverable formats and naming patterns, then checks generated files/hashes. Preparation checklists cannot satisfy requested academic deliverables. File presence never certifies the content of a report or project.
- Source ZIPs include tracked eligible text files only. Binary assets, archives, unknown formats, secrets and build/cache directories are excluded. Review the manifest against deliverable requirements; no secret scanner can mathematically certify arbitrary source text.
- No remote-write implementation is enabled. Even confirmed remote actions are rejected outside dry-run.
- Browser/session operations are single-process per provider profile; close conflicting sessions before syncing. SQLite supports concurrent local readers, but application runs are not a distributed scheduler.
- Deleted external facts are retained; absence from a partial scrape is never interpreted as deletion. Retrieval hashes prevent duplicate fact notifications; full raw authentication pages and network traces are never persisted.

## Development

```powershell
python -m pytest -q
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python -m build
```

Tests use synthetic academic data and temporary repositories, never real credentials. Read-only live probes in `tools/` print structural metadata/counts; `validate_cli.py` exercises local workflows against `.campus`. These tools are opt-in and excluded from normal application execution. Windows sandbox environments may require an approved unsandboxed test run because Python's private temporary-directory ACLs deny the sandbox identity; do not weaken production auth-directory permissions to work around this.

See [architecture](docs/architecture.md), [security](docs/security.md), [integration findings](docs/integrations.md), and [session validation](FINAL_REPORT.md).
