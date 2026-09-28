# Read-only integration findings

Validated on 2026-09-28. These are observations of this account's legitimate application views, not promises that every campus or Moodle configuration behaves identically. No private records or account identifiers belong in this document.

## UTFPR Student Portal — REAL-VALIDATED / PARTIAL

Entry: <https://sistemas2.utfpr.edu.br/dpls/sistema/aluno02/mpmenu.inicio>. Campus: Cornélio Procópio. The authenticated menu naturally supplied `p_unidadelogado=2`; this was discovered, not guessed. Runtime navigation preserves the actual menu parameters rather than constructing account IDs.

The login form can appear after Angular initialization; authentication waits for it before filling environment-provided credentials. `button#logoutButton` verifies the authenticated main page. The observed POST `mpmenu.pcAjaxMenu` fetches the menu and is allowlisted as a read operation. No enrollment or other mutating procedure is allowed.

Menu cards assign `if_navega.src` to academic views. The adapter parses that literal URL as data, restricts host/path and follows only four observed procedures:

| Menu view | Procedure | Normalized coverage |
| --- | --- | --- |
| Boletim | `mpboletim.inicioAluno` | Semester, planned/held/absent class periods, explicit 25% absence-limit formula, reported grades and assessment rows |
| Disciplinas Matriculadas | `mpconfirmacaomatricula.pcTelaAluno` | Course code/name/section, workload hours, regular weekday timetable |
| Histórico Completo | `mphistescol.pcprocessa` | Course attempts, explicit approved/credited completion, missing-course requirements |
| Matrizes Curriculares | `mptabcursograde.inicio` | Curriculum, workload, prerequisites, optional groups and unresolved period gates |

The legacy views declare ISO-8859-1. UTF-8 decoding corrupted headers and prevented reliable parsing; declared-charset decoding fixed it. Nested identity tables must not be confused with academic rows. Asterisks in grade cells are not zeros. Workload hours and attendance class periods are distinct units. Timetable cells with unrecognized/merged structure are skipped, not guessed.

Completion is derived from explicit approved history or the missing-course table, not from merely being absent from current enrollment. Current courses are not assumed passed. Future offerings, equivalency decisions, elective choices and administrative requirements remain unknown. The planner returns a mandatory-subset estimate with blockers, never a confirmed graduation date.

## Moodle — REAL-VALIDATED / PARTIAL

Browser course discovery uses the authenticated `core_course_get_enrolled_courses_by_timeline_classification` AJAX request; the session key remains private. Assignment pages are ordinary read views found on the user's enrolled course pages. Visible Portuguese opening/deadline labels, descriptions, submission tables and attachment links are parsed. Relative countdown rows are excluded from stored submission details to avoid false change notifications.

Observed course names encode code, section and semester; exact matches establish persistent Portal/Moodle mappings. Less certain names are only suggestions. Session-only cookies need explicit private persistence because browser profile persistence alone did not retain the authenticated Moodle session after shutdown.

Activity titles come from `#page-header .page-header-headings h1` in the observed installation. Global `h2` selection instead captured the chat widget or instructor-authored subheadings; the release audit corrected this and real re-synchronization updated the existing title facts without removing their history.

Real PDF attachments were downloaded from observed same-origin `/pluginfile.php/` links and text extracted. Redirects are refused; size/type limits apply; ZIPs are not extracted. A query string such as `forcedownload=1` is not part of the file extension. Linked extracted text is included in work preparation as untrusted evidence.

Existing-token REST support is implemented and allowlisted, but not REAL-VALIDATED without an existing authorized token. Browser coverage does not establish completeness for forums, hidden sections, all course materials, feedback or grading policies.

### Teaching policies and communication continuation

The existing course pages exposed resource views for plans and introductory presentations. Observed resource reads redirect with HTTP 303 to same-origin `pluginfile.php` PDFs. The bounded document adapter follows only that validated transition (or an unambiguous embedded file), not arbitrary redirects or remote hosts. Video resources are excluded. Content hashes cache extracted text. Five real documents supplied evaluation sections; extraction is linked through existing course mappings.

The sources include explicit percentage components, linear formulas, recovery replacements, a summation with unclear weight units, conflicting formula/weight descriptions, and passing thresholds whose units appear inconsistent with the displayed grade scale. CAMPUS preserves literal thresholds, flags discrepancies and does not silently rescale. Three documents support arithmetic scenarios; this does not establish a reliable required-to-pass answer from actual recorded marks. Missing/ambiguous component matches and approval rules remain blockers.

Announcement indexes use `.discussion-list tr[data-discussionid]`. Nine observed titles were synchronized without requesting discussion bodies. Unread counts and tracking actions are excluded from facts. Titles and mail snippets create candidate academic events, not confirmed replacement deadlines. Three submitted assignment views were inspected for feedback structure; they exposed submission-status tables, but no feedback section in that sample. Feedback completeness is therefore unverified, not falsely reported as implemented.

History has separate A/B/C/D/E workload columns: required, attempted, approved/validated, remaining, and approved. Elective-group approval balances can differ from overall validated balances; both are retained with their own meaning. Explicit extension-hour rows may overlap total workload and are not added again. Individual equivalency rows distinguish credited `Sim` from `Não`; failed/cancelled equivalents never confer completion. Curriculum `Período` gates retain an unknown comparison operator instead of being invented prerequisites.

## Institutional Gmail — REAL-VALIDATED / PARTIAL

Manual Google authentication uses a separate persistent browser profile; no Google password is requested or stored by CAMPUS. Authentication is checked against an institutional account indicator and mailbox structure, not profile-file existence. An observed Gmail list-fetch POST (`/sync/u/<number>/i/bv`) is allowlisted; action endpoints are not.

Academic search is deterministic before reading visible thread snippets. The thread identifier appears on a descendant element in the observed DOM. Browser mode never opens threads because that can change read status. Coverage is the first visible result page only, not the full mailbox or full messages.

Derived analysis stores topics, date mentions and deterministic course candidates alongside source evidence IDs. It is intentionally PARTIAL: an ambiguous snippet date does not overwrite an assignment deadline. Reanalysis of unchanged snippets produces no new changes.

Optional IMAP uses TLS, read-only mailbox selection and `BODY.PEEK`, including MIME headers for correct charset/transfer decoding. It requires an already institution-authorized app password and has not been live-validated in this session. Google Cloud project creation is not required by either implemented path. Organization policy may make IMAP unavailable.

## Local Git and optional GitHub

Git discovery and metadata reads were REAL-VALIDATED in the configured project directory. NUL-delimited tracked filenames are preserved until parsed. No source repository was modified. Automatic source packages require explicit assignment/repository linking.

GitHub uses an already authenticated `gh` installation if available. It remains BLOCKED here because `gh` is unavailable; installing or authenticating an unrelated account was not necessary for the local workflow.

## Repeatability and safety

Consecutive real Portal, Moodle and Gmail synchronizations produced zero value changes for unchanged sources. Provider status remains PARTIAL where source coverage is incomplete even when authentication is HEALTHY. All remote development activity was read-only, apart from necessary authentication/session establishment; no messages, submissions, enrollments or account-setting changes were performed.

Debugging saves sanitized operation metadata only. Raw authenticated HTML, screenshots, cookies and traces are not published or used as test fixtures. Browser sessions may expire; use `campus auth <provider>` and complete any MFA/SSO/CAPTCHA manually.
