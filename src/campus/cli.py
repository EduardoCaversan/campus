import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from campus import __version__
from campus.artifacts import generate_document, package_repository, read_document
from campus.config import load_config
from campus.engines import attendance, attendance_view, correlate, grade_view, grades
from campus.models import CampusError, Fact
from campus.reporting import write_report
from campus.security import Capability, authorize, clean, digest, inside, private_dir, redact
from campus.service import Campus

app = typer.Typer(
    help="CAMPUS — local academic evidence and automation",
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
console = Console(highlight=False)


def service(ctx):
    return ctx.obj["campus"]


def output(ctx, data):
    data = clean(data)
    if ctx.obj["json"]:
        typer.echo(json.dumps(data, ensure_ascii=True, default=str))
    else:
        render(data)


def render(data, depth=0):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                console.print(
                    "  " * depth + key.replace("_", " ").capitalize(), style="cyan", markup=False
                )
                render(value, depth + 1)
            elif value is not None:
                console.print("  " * depth + f"{key.replace('_', ' ')}: {value}", markup=False)
    elif isinstance(data, list):
        if not data:
            console.print("  " * depth + "No local records", style="dim")
        for item in data:
            render(item, depth)
            if isinstance(item, dict):
                console.print()
    else:
        console.print("  " * depth + str(data), markup=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    home: Path | None = typer.Option(None, help="Private data directory; defaults to ~/.campus"),
    config: Path | None = typer.Option(None, help="TOML configuration"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    version: bool = typer.Option(False, "--version"),
):
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    campus = Campus(load_config(home, config))
    ctx.obj = {"campus": campus, "json": json_output}
    ctx.call_on_close(campus.store.close)
    if ctx.invoked_subcommand is None:
        if not sys.stdin.isatty() or json_output:
            output(ctx, campus.status())
        else:
            console.print("CAMPUS", style="bold cyan")
            console.print("Local academic agent · /status /sync /work /help /exit", style="dim")
            while True:
                try:
                    question = console.input("[cyan]campus > [/]").strip()
                    if question in {"/exit", "/quit", "exit"}:
                        break
                    if not question:
                        continue
                    if question == "/help":
                        console.print(
                            "Ask about deadlines, grades, attendance, changes or graduation. /sync reads providers; /work creates local preparation files.",
                            markup=False,
                        )
                    else:
                        action = {
                            "/status": campus.status,
                            "/sync": campus.sync,
                            "/work": campus.work,
                        }.get(question)
                        output(ctx, action() if action else campus.ask(question))
                except (EOFError, KeyboardInterrupt):
                    break
                except CampusError as exc:
                    output(ctx, {"state": exc.state, "message": redact(str(exc))})


@app.command()
def setup(
    ctx: typer.Context,
    authenticate: bool = typer.Option(
        True,
        "--authenticate/--no-authenticate",
        help="Open browser sign-in for providers that need authentication",
    ),
    offline: bool = typer.Option(
        False, "--offline", help="Initialize storage without network access"
    ),
):
    campus = service(ctx)
    config_path = campus.config.home / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            '# CAMPUS configuration. Secrets belong in environment variables or a gitignored .env.\ntimezone = "America/Sao_Paulo"\nproject_dirs = []\n# browser_channel = "msedge"\nmail_mode = "browser"\nllm_provider = "none"\n',
            encoding="utf-8",
        )
    auth_results = []
    if authenticate and not offline:
        from campus.providers.browser import auth

        for provider in ("portal", "moodle", "mail"):
            try:
                existing = campus.providers()[provider].check()
                if existing.authenticated:
                    auth_results.append(
                        {"provider": provider, "state": "HEALTHY", "authenticated": True}
                    )
                    continue
            except Exception:
                pass  # The explicit authentication flow supplies the actionable result below.
            if not ctx.obj["json"]:
                console.print(
                    f"Opening {provider} sign-in. Complete any MFA or CAPTCHA in the browser.",
                    markup=False,
                )
            try:
                auth_results.append(auth(campus.config, provider))
            except CampusError as exc:
                auth_results.append(
                    {"provider": provider, "state": exc.state.value, "message": str(exc)}
                )
    if offline:
        output(
            ctx,
            {
                "state": "PARTIAL",
                "database": "INITIALIZED",
                "authentication": "NOT VERIFIED",
                "config": str(config_path),
                "next": "campus auth portal; campus auth moodle; campus auth mail; campus sync",
            },
        )
    else:
        result = campus.sync(force=True)
        result["authentication"] = auth_results
        output(ctx, result)
        if result["state"] != "COMPLETED":
            raise typer.Exit(2)


@app.command()
def sync(ctx: typer.Context, provider: str | None = None, force: bool = False):
    """Read external sources; persist evidence and changes independently per provider."""
    result = service(ctx).sync(provider, force)
    output(ctx, result)
    if result["state"] != "COMPLETED":
        raise typer.Exit(2)


@app.command()
def status(ctx: typer.Context):
    campus = service(ctx)
    data = campus.status()
    if ctx.obj["json"]:
        output(ctx, data)
        return
    console.print("CAMPUS · UTFPR", style="bold cyan")
    console.print(
        f"Semester: {', '.join(data['semester']) if isinstance(data['semester'], list) else data['semester']} · Courses: {data['courses']} · Unread changes: {data['changes']}",
        markup=False,
    )
    table = Table("State", "Deadline", "Assignment", "Freshness")
    for item in data["deadlines"][:12]:
        table.add_row(
            item["state"],
            item["effective_deadline"] or "UNKNOWN",
            item["name"],
            item["freshness"]["state"],
        )
    console.print(table)
    for health in data["last_sync"]:
        console.print(
            f"{health['provider']}: {health['state']} · last observed data: {health['last_data_sync'] or 'UNKNOWN'}",
            markup=False,
        )
    if not data["last_sync"]:
        console.print("UNKNOWN · No provider synchronization recorded. Run campus setup.")
    warnings = [
        a
        for a in data["attendance"]
        if a.get("state") in {"UNKNOWN", "CONFLICT"} or a.get("remaining_allowance", 99) <= 2
    ]
    console.print(
        f"Attendance: {len(warnings)} courses need review or lack sufficient data.", markup=False
    )


@app.command()
def courses(ctx: typer.Context):
    output(ctx, service(ctx).store.entities("course"))


@app.command()
def course(ctx: typer.Context, identifier: str):
    output(
        ctx,
        service(ctx).store.entities("course", identifier)
        or {"state": "UNKNOWN", "message": "No matching course"},
    )


@app.command()
def deadlines(
    ctx: typer.Context,
    days: int | None = typer.Option(None, min=1),
    include_submitted: bool = typer.Option(False, "--all"),
):
    output(ctx, service(ctx).deadlines(days, include_submitted))


@app.command("grades")
def grades_command(ctx: typer.Context):
    campus = service(ctx)
    output(ctx, grade_view(campus.store, campus.config.stale_hours))


@app.command("grade-scenario")
def grade_scenario(ctx: typer.Context, components: Path, target: float = 6, scale: float = 10):
    """Calculate from an explicit JSON array of {weight, grade}; null grade is unknown."""
    output(ctx, grades(json.loads(components.read_text(encoding="utf-8")), target, scale))


@app.command("attendance")
def attendance_command(
    ctx: typer.Context, miss: float = typer.Option(0, min=0), day: str | None = None
):
    campus = service(ctx)
    if day:
        from campus.engines import attendance_day_view

        if miss:
            raise CampusError(
                "Use either --day for timetable-derived units or --miss for explicit units"
            )
        output(ctx, attendance_day_view(campus.store, day, campus.config.stale_hours))
        return
    output(ctx, attendance_view(campus.store, campus.config.stale_hours, miss))


@app.command("attendance-scenario")
def attendance_scenario(
    ctx: typer.Context,
    total: float,
    absences: float,
    minimum: float,
    held: float | None = None,
    miss: float = 0,
):
    """Explicit units; minimum is a fraction such as .75, never an inferred rule."""
    output(ctx, attendance(total, absences, minimum, held, miss))


@app.command()
def plan(
    ctx: typer.Context,
    max_load: int = typer.Option(360, min=1),
    start_term: int = typer.Option(1, min=1, max=2),
):
    output(ctx, service(ctx).plan(max_load, start_term))


@app.command()
def changes(
    ctx: typer.Context, acknowledge: bool = False, limit: int = typer.Option(100, min=1, max=10000)
):
    output(ctx, service(ctx).store.changes(acknowledge, limit))


@app.command()
def evidence(ctx: typer.Context, identifier: str):
    output(ctx, service(ctx).store.evidence(identifier))


@app.command()
def mail(ctx: typer.Context):
    output(ctx, service(ctx).store.entities("mail"))


@app.command("analyze-mail")
def analyze_mail_command(ctx: typer.Context):
    """Classify stored academic messages and link course candidates without model calls."""
    from campus.mail_analysis import analyze_mail

    output(ctx, analyze_mail(service(ctx).store))


@app.command()
def repos(ctx: typer.Context):
    output(ctx, service(ctx).store.entities("repository"))


@app.command()
def work(ctx: typer.Context, identifier: str = ""):
    result = service(ctx).work(identifier)
    output(ctx, result)
    if result["state"] != "COMPLETED":
        raise typer.Exit(2)


@app.command()
def report(ctx: typer.Context, pdf: bool = False):
    campus = service(ctx)
    rows = campus.store.connection.execute(
        "SELECT * FROM runs ORDER BY created_at DESC,rowid DESC LIMIT 1"
    ).fetchall()
    result = (
        dict(rows[0])
        if rows
        else write_report(campus.config, campus.store, "status", campus.status())
    )
    if pdf:
        source = Path(result.get("report_path") or result["report"])
        result["pdf"] = generate_document(
            source.read_text(encoding="utf-8"), source.with_suffix(".pdf")
        )
    output(ctx, result)


@app.command()
def doctor(ctx: typer.Context):
    result = service(ctx).doctor()
    output(ctx, result)
    if result["state"] != "HEALTHY":
        raise typer.Exit(2)


@app.command()
def auth(
    ctx: typer.Context,
    provider: str,
    wait: int = typer.Option(180, min=10, max=600),
    campus: str | None = typer.Option(None),
):
    from campus.providers.browser import auth as authenticate

    if not ctx.obj["json"]:
        console.print(
            f"Opening {provider} sign-in. Complete MFA/CAPTCHA in the browser; CAMPUS will wait up to {wait}s.",
            markup=False,
        )
    if campus:
        service(ctx).config.portal_campus = campus
    result = authenticate(service(ctx).config, provider, wait)
    output(ctx, result)
    if not result.get("authenticated"):
        raise typer.Exit(2)


@app.command()
def ask(ctx: typer.Context, question: str):
    output(ctx, service(ctx).ask(question))


@app.command("import")
def import_facts(ctx: typer.Context, file: Path):
    """Import explicitly supplied normalized evidence; never auto-import source instructions."""
    if not file.is_file() or file.stat().st_size > 10_000_000:
        raise CampusError("Evidence import must be a JSON file under 10 MB")
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        facts = [Fact.model_validate(f) for f in raw]
    except Exception:
        raise CampusError(
            "Invalid evidence JSON; validation details suppressed for privacy"
        ) from None
    output(
        ctx,
        {"state": "COMPLETED", "facts": len(facts), "changes": service(ctx).store.ingest(facts)},
    )


@app.command("import-document")
def import_document(ctx: typer.Context, file: Path):
    text = read_document(file)
    subject = "document:" + digest(str(file.resolve()))[:20]
    result = service(ctx).store.ingest(
        [
            Fact(
                subject=subject,
                kind="document",
                field="text",
                value=text,
                source="filesystem",
                external_ref=str(file.resolve()),
                excerpt=text,
            )
        ]
    )
    output(
        ctx,
        {
            "state": "PARTIAL",
            "subject": subject,
            "changes": result,
            "message": "Document text imported as untrusted evidence; no academic rules inferred",
        },
    )


@app.command("map-course")
def map_course(ctx: typer.Context, alias: str, canonical: str):
    store = service(ctx).store
    ids = {e["id"] for e in store.entities("course")}
    if alias not in ids or canonical not in ids:
        raise CampusError("Both course identifiers must exist")
    store.map(alias, canonical, 1, "Explicit local mapping by user")
    output(ctx, {"state": "COMPLETED", "alias": alias, "canonical": canonical})


@app.command("correlate")
def correlate_command(ctx: typer.Context):
    output(ctx, correlate(service(ctx).store))


@app.command("link-repo")
def link_repo(ctx: typer.Context, assignment: str, repository: Path):
    campus = service(ctx)
    if assignment not in {e["id"] for e in campus.store.entities("assignment")}:
        raise CampusError("Assignment identifier must exist")
    repository = repository.resolve()
    if not (repository / ".git").exists() or not any(
        repository.is_relative_to(p) for p in campus.config.project_dirs
    ):
        raise CampusError("Repository must exist inside configured project_dirs")
    campus.store.ingest(
        [
            Fact(
                subject=assignment,
                kind="assignment",
                field="repository",
                value=str(repository),
                source="local",
                external_ref="local:repository-mapping",
            )
        ]
    )
    output(ctx, {"state": "COMPLETED", "message": "Local assignment-repository mapping stored"})


@app.command()
def artifact(
    ctx: typer.Context, name: str, source: Path | None = None, repository: Path | None = None
):
    """Generate MD/TXT/PDF/DOCX from --source, or source ZIP from --repository."""
    campus = service(ctx)
    root = private_dir(campus.config.artifacts)
    target = inside(root, root / name)
    if target.suffix.lower() == ".zip" and repository:
        result = package_repository(repository, target)
    elif source and not repository:
        result = generate_document(read_document(source), target)
    else:
        raise CampusError("Choose --source for a document or --repository for ZIP")
    from campus.artifacts import artifact_manifest

    manifest = artifact_manifest(
        target.parent,
        [result],
        filename=target.name + ".manifest.json",
        repository=str(repository.resolve()) if repository else None,
    )
    result["manifest"] = str(manifest)
    output(ctx, {"state": "FAILED" if result["validation"] == "FAILED" else "COMPLETED", **result})


@app.command("capability")
def capability_command(ctx: typer.Context, capability: Capability):
    """Inspect capability policy; remote actions always remain dry-runs."""
    output(ctx, authorize(capability))


@app.command("analyze-policies")
def analyze_policies_command(ctx: typer.Context):
    """Extract course-specific grading policies from locally synchronized teaching documents."""
    from campus.policies import analyze_policies

    output(ctx, analyze_policies(service(ctx).store))


@app.command("grade-policy")
def grade_policy_command(
    ctx: typer.Context,
    identifier: str = "",
    component: str | None = None,
    set_grade: list[str] = typer.Option([], "--set"),
    recovery: float | None = typer.Option(None, "--recovery"),
):
    """Use evidence-backed policy; e.g. grade-policy CODE --set P1=7 --component P2."""
    from campus.policies import policy_grade

    overrides = {}
    for item in set_grade:
        key, sep, value = item.partition("=")
        if not sep or not key or not value:
            raise CampusError("Use --set COMPONENT=GRADE")
        overrides[key.upper()] = value.replace(",", ".")
    campus = service(ctx)
    output(
        ctx,
        policy_grade(
            campus.store,
            identifier,
            overrides,
            component.upper() if component else None,
            campus.config.stale_hours,
            recovery_grade=recovery,
        ),
    )


@app.command("requirements")
def requirements_command(ctx: typer.Context):
    """Explicit source-backed curriculum balances and individual equivalence decisions."""
    campus = service(ctx)
    output(
        ctx,
        {
            "requirements": campus.store.entities("requirement"),
            "equivalencies": campus.store.entities("equivalence"),
        },
    )


@app.command("announcements")
def announcements_command(ctx: typer.Context):
    output(ctx, service(ctx).store.entities("announcement"))


@app.command("events")
def events_command(ctx: typer.Context):
    from campus.events import analyze_events

    campus = service(ctx)
    analysis = analyze_events(campus.store)
    output(ctx, {**analysis, "events": campus.store.entities("event")})


@app.command()
def download(ctx: typer.Context, identifier: str):
    """Download known Moodle assignment attachments to private, content-addressed storage."""
    from campus.providers.downloads import download_moodle

    campus = service(ctx)
    output(ctx, download_moodle(campus.config, campus.store, identifier))


def run():
    try:
        app()
    except CampusError as exc:
        typer.echo(json.dumps({"state": exc.state.value, "message": redact(str(exc))}), err=True)
        raise SystemExit(2) from None
    except Exception as exc:
        typer.echo(
            json.dumps(
                {
                    "state": "FAILED",
                    "message": f"Operation failed ({type(exc).__name__}); details suppressed for privacy",
                }
            ),
            err=True,
        )
        raise SystemExit(1) from None
