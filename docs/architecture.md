# Architecture

## Data flow

```text
Portal / Moodle / Mail / Git / documents
                  |
           isolated providers
                  |
      normalized Fact + source evidence
                  |
 SQLite current assertions + immutable versions + snapshots
                  |
   deterministic engines / local work / reports
                  |
            terminal CLI / agent
```

`models.py` defines validated observations and provider outcomes. `providers/` owns external transport and parsing. Domain engines have no Playwright selectors. `service.py` coordinates services; `cli.py` handles presentation. `artifacts.py` performs bounded local generation. `security.py` centralizes redaction, paths, package inspection and capability decisions.

`rules.py` models grading, attendance and curriculum-rule values inside the existing evidence envelope. `policies.py` compiles a bounded linear arithmetic grammar to Decimal coefficients, matches only exact assessment identifiers/names, and evaluates scenarios without code execution. Policy source identity uses the stable Moodle resource view: revisions replace derived current pointers while preserving immutable document/evidence history. Independent documents remain independent sources and conflicts remain visible.

`events.py` keeps announcement/email interpretations as candidate events, not authoritative deadline mutations. `deliverables.py` separates explicit requirements from mentions and file validation from academic-content approval. Portal workload columns are preserved separately; approved, validated, group-balance and overall-balance hours are not interchangeable.

## Persistence and evidence

An assertion is identified by `(subject, field, source, external_ref)`. `evidence` holds immutable versions. `current` points to the latest source assertion and last successful observation. `snapshots` are content-addressed, sanitized excerpts or structured values, not raw authenticated pages. `changes` contains semantic value changes; refreshing an identical value advances observation time without notifying again. Older imports cannot overwrite newer observations.

Different source assertions coexist. Entity views group canonical course identities and preserve all distinct field values. Conflicting deadlines select the earliest only for the explicitly labeled conservative display. Acknowledgement affects the local notification queue, never evidence history. Absence from an incomplete scrape does not delete anything.

SQLite uses transactions, foreign keys, WAL, a busy timeout and schema-version checking. Back up the database using SQLite's backup API or after closing CAMPUS; do not copy a live DB without its WAL. Auth profiles are independently sensitive and should not be included in ordinary backups without protection.

## Deterministic engines

- Decimal arithmetic for grades and absence allowances; all policy inputs must be supplied.
- Prerequisite cycle detection, earlier-term completion, workload caps, term offerings and interval-overlap checks. Plans are feasible greedy estimates, not globally optimal plans.
- Exact normalized names yield course suggestions. Automatic joins require matching code, semester and section. Explicit mappings persist and reject cycles.
- Stable hashes/version comparisons for changes and semantic caching.
- Regular-timetable absence scenarios preserve period units and unknown calendar exceptions. Curriculum planning separates known mandatory courses from unresolved gates and elective/non-course requirements.
- Mail topic/date extraction and exact course-reference candidates retain source evidence IDs; inferred mentions do not become authoritative deadline facts.
- ZIP entries and document metadata use stable timestamps for repeatable generation. Run manifests have their actual creation time.

## LLM boundary

`LLMProvider` is an interface. The initial implementation supports local Ollama; the default is disabled. Retrieval provides a bounded subset of evidence. System instructions label source text as untrusted, but the stronger protection is structural: the model has no shell, filesystem mutation, browser, credentials, or submission tool. Its answer cannot become an executable plan. Citation IDs are checked; this does not prove every semantic claim is correct, so model interpretations are labeled for review.

## Provider isolation and health

Each provider returns its own state, authentication verification, facts and warnings. Exceptions are reduced to safe operation/type messages. Existing records survive failures. `doctor` performs live checks and does not update data-sync timestamps. `status` reads SQLite only. Sync intervals cache recent partial or healthy observations while preserving their original completeness state.

Moodle prioritizes existing-token REST and the authenticated course-list AJAX read method, with DOM extraction for assignments. Portal follows discovered view links and explicit headers. Gmail uses a manually authenticated profile and an allowlisted observed list-fetch operation; thread opening and action endpoints are excluded. IMAP uses `EXAMINE` and `BODY.PEEK`.

## Decisions

See [ADR 001](adr/001-python-local-first.md). This release deliberately blocks remote writes entirely. It also does not run arbitrary repository build scripts automatically: those scripts are executable code and their trust cannot be derived from Moodle instructions.
