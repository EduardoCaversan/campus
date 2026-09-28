# ADR 001: Python, SQLite and explicit provider boundaries

Status: accepted, 2026-09-28.

The initial repository contained only `.gitignore`; Python 3.13, Node and Git were available. There was no existing application architecture to preserve.

Use Python 3.12+ because its standard library provides SQLite, Decimal, email/IMAP, ZIP and filesystem tools. Playwright supplies browser interoperability, Pydantic validates input envelopes, Typer/Rich provide the terminal interface, and established PDF/DOCX libraries support local artifacts. A Python package and console entry point avoid a browser UI or an always-running server.

Use SQLite as the normalized local authority. Keep source-specific transport separate from pure engines. Store versioned assertions rather than overwrite a single preferred source; disagreements and historical changes matter academically.

Use a private browser profile for each service. Session cookies must be saved explicitly because closing a persistent Chromium context did not retain Moodle's session-only cookie in live testing. Store these only inside private auth directories. Do not capture screenshots, raw HTML or traces by default; sanitized operation metadata is the safer diagnostic baseline.

Use local-only semantic inference initially. External model support can implement the protocol later, with an explicit data-egress policy. No model is required for synchronization, calculations, planning, evidence, changes, reports or artifacts.

Costs: browser adapters need upkeep; Windows profiles may encounter exclusive locks; SQLite data is not encrypted by the application; university-specific curricula and regulations must be supplied or parsed, not inferred.
