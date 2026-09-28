# Security boundaries

## Credentials and local privacy

`python-dotenv` loads only the current directory's `.env`, does not interpolate values, and never overrides existing process variables. Credential-presence checks return PRESENT/MISSING only. Values are consumed only by the matching authentication adapter and redaction/secret-detection code. The LLM receives neither the environment nor browser state.

`.env`, browser profiles, cookies, databases, reports, downloads, traces and generated artifacts are gitignored. Browser profiles use private directories (mode 0700; Windows Python applies owner/system ACLs where supported). Session cookies are sensitive and are stored separately inside each private profile because Chromium otherwise dropped session-only Moodle cookies between runs. The application does not encrypt the database or cookie JSON. Protect the machine, its disk, backups and account permissions.

Use `~/.campus` outside cloud-synced folders for ongoing use. This development workspace is in OneDrive, so its gitignored `.campus` is not guaranteed to stay off cloud storage. Gitignore protects Git, not OneDrive. Do not publish reports: they intentionally contain academic evidence.

## External data is untrusted

Mail, Moodle descriptions, portal pages, files and extracted documents are data. They cannot choose commands, output paths, credentials, capabilities or remote actions. Model output has no execution path. Prompt-injection resistance is enforced by tool isolation, not merely an instruction in a prompt.

Source strings are sanitized before persistence/presentation. Redaction covers loaded authentication values, common token/password patterns, private-key blocks and URL userinfo. Terminal controls are removed and Rich markup is disabled for external content. No generic scanner detects every possible secret; report privacy remains necessary.

Exceptions are reduced to operation names and exception types. Pydantic validation details and transport exceptions are not printed because they can echo input values or token-bearing URLs. Diagnostics contain provider/operation/type/time only. No default HTML, screenshots, HARs or Playwright traces are captured.

## Remote access

No remote-write executor is enabled. `WRITE_REMOTE`, `SUBMIT` and `SEND_EMAIL` return dry-run/confirmation requirements; an attempted non-dry-run is rejected even with confirmation. Enabling real writes in a future release requires a new reviewed execution layer with target-specific confirmation and replay protection.

Browser sync blocks POSTs except explicitly observed read operations: the UTFPR menu fetch and Gmail list-view batch fetch. Moodle course-list AJAX is called directly with a fixed read method; token-based RPC has an explicit method allowlist. Authentication has a separate browser flow so legitimate credential submissions and human SSO/MFA can proceed. CAMPUS never automates account changes or Google password entry.

Browser read requests may cause ordinary server access/audit logs. Gmail threads are not opened because opening can mark them read. The Gmail adapter confirms an institutional account marker before reading rows. IMAP uses SSL, read-only INBOX and BODY.PEEK; no SMTP client exists.

Attachment downloads are limited to links already present in local Moodle assignment evidence, on the configured HTTPS Moodle origin, under `pluginfile.php`. Redirects are rejected, downloads are capped at 20 MB, and files are named by their content hash. Archives are never automatically extracted, and macros/executables are not run. PDF/DOCX parsing remains an attack surface: keep dependencies updated and treat output as untrusted. Parsing has file/page/expanded-size limits but is not a full sandbox against malicious library inputs.

## Local execution and artifacts

Git subprocesses use argument arrays and no shell; the adapter permits read commands only, disables hooks/fsmonitor/external diff configuration, and never modifies worktrees. Repository build/test scripts are not executed automatically from source instructions.

ZIP generation uses tracked files only, rejects symlinks/junctions and traversal, allows known text formats, excludes sensitive/cache paths and scans content. Binary assets/unknown formats require review. Size limits bound files and packages. Each generated package lists exclusions; a source ZIP is not a certificate that an assignment is complete.

Artifact paths must remain under the configured artifact directory; existing artifacts are not overwritten. Generation validates ZIP CRCs, DOCX structure, PDF readability and hashes. Reports are sanitized and stored locally.

## Operational guidance

- Do not share `.campus`, `.env`, auth profiles or academic reports.
- Do not run multiple browser operations against the same provider profile.
- Expired or rejected sessions return BLOCKED; complete authentication normally.
- Review package exclusions and academic content before manually submitting anything.
- On a compromised workstation, revoke sessions through the provider's normal account-security interface. CAMPUS does not automate revocation or account-setting changes.
