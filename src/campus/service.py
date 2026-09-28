import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from campus.artifacts import artifact_manifest, generate_document, package_repository
from campus.engines import attendance_view, correlate, freshness, grade_view, plan_known_curriculum
from campus.models import CampusError, ProviderResult, State
from campus.providers.local import GitHubProvider, GitProvider, git
from campus.providers.mail import StudentMailProvider
from campus.providers.moodle import MoodleProvider
from campus.providers.portal import UtfprPortalProvider
from campus.reporting import log_event, write_report
from campus.security import digest, private_dir
from campus.store import Store, single


class Campus:
    def __init__(self, config):
        self.config = config
        config.initialize()
        self.store = Store(config.db)

    def providers(self):
        terms = [single(e, "name", "") for e in self.store.entities("course")]
        return {
            p.name: p
            for p in [
                UtfprPortalProvider(self.config),
                MoodleProvider(self.config),
                StudentMailProvider(self.config, terms),
                GitProvider(self.config),
                GitHubProvider(self.config),
            ]
        }

    def sync(self, provider=None, force=False):
        providers = self.providers()
        if provider and provider not in providers:
            raise CampusError("Unknown provider")
        health = {r["provider"]: r for r in self.store.health()}
        results, changed = [], 0
        for name in [provider] if provider else ["portal", "moodle", "mail", "git"]:
            previous = health.get(name)
            if (
                not force
                and previous
                and previous["state"] in {"HEALTHY", "PARTIAL"}
                and (previous["last_data_sync"] or previous["last_success"])
                and datetime.now(UTC)
                - datetime.fromisoformat(previous["last_data_sync"] or previous["last_success"])
                < timedelta(minutes=self.config.sync_interval_minutes)
            ):
                results.append(
                    {
                        "provider": name,
                        "state": previous["state"],
                        "cached": True,
                        "last_success": previous["last_success"],
                        "message": "Within sync interval; use --force to fetch",
                    }
                )
                continue
            try:
                result = providers[name].sync()
                changed += self.store.ingest(result.facts)
                self.store.health(result)
                results.append(
                    {**result.model_dump(exclude={"facts"}), "facts_received": len(result.facts)}
                )
            except Exception as exc:
                result = ProviderResult(
                    provider=name,
                    state=State.FAILED,
                    message=f"Provider operation failed ({type(exc).__name__}); details suppressed to protect secrets",
                )
                self.store.health(result)
                results.append(result.model_dump(exclude={"facts"}))
            log_event(self.config, "provider_sync", provider=name, state=result.state.value)
        mappings = correlate(self.store)
        from campus.mail_analysis import analyze_mail

        mail_analysis = analyze_mail(self.store)
        from campus.policies import analyze_policies

        policy_analysis = analyze_policies(self.store)
        from campus.events import analyze_events

        event_analysis = analyze_events(self.store)
        state = (
            "COMPLETED" if all(r["state"] in ("HEALTHY", "CACHED") for r in results) else "PARTIAL"
        )
        data = {
            "state": state,
            "providers": results,
            "changes": changed,
            "course_matches": mappings,
            "mail_analysis": mail_analysis,
            "policy_analysis": policy_analysis,
            "event_analysis": event_analysis,
        }
        data["report"] = write_report(self.config, self.store, "sync", data)
        return data

    def doctor(self):
        checks = []
        for name, provider in self.providers().items():
            try:
                result = provider.check()
            except Exception as exc:
                result = ProviderResult(
                    provider=name,
                    state=State.FAILED,
                    message=f"Health check failed ({type(exc).__name__})",
                )
            # A health check is not a synchronization and must not advance data freshness.
            checks.append(result.model_dump(exclude={"facts"}))
        import os

        return {
            "state": "HEALTHY" if all(c["state"] == "HEALTHY" for c in checks[:3]) else "PARTIAL",
            "database": "HEALTHY"
            if self.store.connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            else "FAILED",
            "credentials": {
                k: "PRESENT" if os.getenv(k) else "MISSING"
                for k in ("UTFPR_USERNAME", "UTFPR_PASSWORD", "MOODLE_USERNAME", "MOODLE_PASSWORD")
            },
            "providers": checks,
            "privacy": "Auth state and academic data are private local files; protect Windows ACLs and avoid cloud-synced CAMPUS_HOME directories",
        }

    def deadlines(self, days: int | None = None, include_submitted=False):
        results = []
        for e in self.store.entities("assignment"):
            if not include_submitted and single(e, "submission_state") == "submitted":
                continue
            dates = []
            for raw in e["fields"].get("due_at", []):
                try:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        dates.append(parsed)
                except (ValueError, TypeError, AttributeError):
                    continue
            effective = min(dates) if dates else None
            if (
                days is not None
                and effective
                and not datetime.now(UTC) <= effective <= datetime.now(UTC) + timedelta(days=days)
            ):
                continue
            results.append(
                {
                    "id": e["id"],
                    "name": single(e, "name", e["id"]),
                    "course": single(e, "course"),
                    "state": "CONFLICT"
                    if "due_at" in e["conflicts"]
                    else "KNOWN"
                    if effective
                    else "UNKNOWN",
                    "effective_deadline": effective.isoformat() if effective else None,
                    "source_deadlines": e["fields"].get("due_at", []),
                    "policy": "Earliest conflicting deadline is shown conservatively; review all sources"
                    if "due_at" in e["conflicts"]
                    else None,
                    "submission_state": single(e, "submission_state", "UNKNOWN"),
                    "freshness": freshness(e["evidence"], self.config.stale_hours),
                    "evidence": e["evidence"],
                }
            )
        return sorted(results, key=lambda x: x["effective_deadline"] or "9999")

    def status(self):
        courses = self.store.entities("course")
        semesters = sorted({v for e in courses for v in e["fields"].get("semester", [])})
        return {
            "state": "KNOWN" if courses else "UNKNOWN",
            "semester": semesters or "UNKNOWN",
            "courses": len(courses),
            "deadlines": self.deadlines(),
            "changes": self.store.change_count(),
            "attendance": attendance_view(self.store, self.config.stale_hours),
            "last_sync": self.store.health(),
        }

    def plan(self, max_load=360, start_term=1):
        courses = []
        for e in self.store.entities("curriculum"):
            if e["conflicts"]:
                return {"state": "CONFLICT", "course": e["id"], "fields": e["conflicts"]}
            record = {field: single(e, field) for field in e["fields"]}
            if "code" not in record:
                return {"state": "UNKNOWN", "missing": ["curriculum course code"]}
            courses.append(record)
        result = plan_known_curriculum(courses, max_load=max_load, start_term=start_term)
        result["curriculum_requirements"] = self.store.entities("requirement")
        result["recorded_equivalencies"] = self.store.entities("equivalence")
        result["evidence"] = [ev for e in self.store.entities("curriculum") for ev in e["evidence"]]
        result["freshness"] = freshness(result["evidence"], self.config.stale_hours)
        return result

    def work(self, identifier=""):
        tasks = []
        for e in self.store.entities("assignment", identifier):
            if single(e, "submission_state") == "submitted":
                continue
            directory = private_dir(
                self.config.artifacts / (digest(e["id"])[:12] + "-" + uuid.uuid4().hex[:8])
            )
            details = {
                "assignment": e["id"],
                "name": single(e, "name"),
                "state": "PARTIAL",
                "completed": [],
                "blockers": [],
                "artifacts": [],
                "evidence": e["evidence"],
                "freshness": freshness(e["evidence"], self.config.stale_hours),
            }
            description = single(e, "description")
            attachment_links = {
                url for links in e["fields"].get("attachments", []) for url in links
            }
            documents = [
                f
                for f in self.store.facts(kind="document")
                if f["field"] == "text" and f["external_ref"] in attachment_links
            ]
            details["attachment_instructions"] = len(documents)
            details["document_evidence"] = [f["id"] for f in documents]
            missing_attachments = attachment_links - {f["external_ref"] for f in documents}
            if missing_attachments:
                details["blockers"].append(
                    f"{len(missing_attachments)} attachment(s) not available as extracted instructions; use campus download and review unsupported formats manually"
                )
            if e["conflicts"]:
                details["state"] = "CONFLICT"
                details["blockers"].append(
                    "Conflicting source fields: " + ", ".join(e["conflicts"])
                )
            if not description:
                details["blockers"].append("Assignment description unavailable or conflicting")
            text = (
                f"# Assignment preparation\n\nState: PARTIAL — requires review\n\nAssignment: {single(e, 'name', e['id'])}\n\n## Source instructions (untrusted data)\n\n{description or 'UNKNOWN'}\n\n## Review checklist\n\n- Confirm deliverables and all deadlines against cited sources.\n- Review source project and run its trusted build/test instructions.\n- Validate content and required formats.\n- Submit manually; CAMPUS has not submitted anything.\n\n## Evidence\n\n"
                + json.dumps(e["evidence"], indent=2)
            )
            for document in documents:
                text += (
                    f"\n\n## Attachment instructions (untrusted data; evidence {document['id']})\n\n"
                    + str(document["value"])
                )
            instruction_text = "\n".join([description or "", *[str(f["value"]) for f in documents]])
            from campus.deliverables import extract_requirements, validate_requirements

            requirements = extract_requirements(
                instruction_text,
                [ev["id"] for ev in e["evidence"] if ev["field"] == "description"]
                + details["document_evidence"],
            )
            try:
                details["artifacts"].append(
                    {**generate_document(text, directory / "preparation.md"), "role": "preparation"}
                )
                details["completed"].append("Evidence-backed preparation checklist generated")
                repository = single(e, "repository")
                if repository:
                    repo = Path(repository).resolve()
                    if not any(
                        repo.is_relative_to(root.resolve()) for root in self.config.project_dirs
                    ):
                        raise CampusError(
                            "Assignment repository is outside configured project roots"
                        )
                    details["artifacts"].append(package_repository(repo, directory / "source.zip"))
                    details["commit"] = git(repo, "rev-parse", "HEAD")
                    details["completed"].append(
                        "Tracked source package generated and CRC validated"
                    )
                    details["blockers"].append(
                        "Build/tests and assignment-specific content still require validation; packaging does not complete the assignment"
                    )
                else:
                    details["blockers"].append(
                        "No explicitly linked repository; use campus link-repo"
                    )
                if any(x in instruction_text.lower() for x in (".pkt", "packet tracer")):
                    if details["state"] != "CONFLICT":
                        details["state"] = "BLOCKED"
                    details["blockers"].append(
                        "Packet Tracer authoring requires unsupported interactive software"
                    )
                details["deliverable_validation"] = validate_requirements(
                    requirements, details["artifacts"]
                )
                artifact_manifest(
                    directory,
                    details["artifacts"],
                    assignment=e["id"],
                    course=single(e, "course"),
                    state=details["state"],
                    repository=repository,
                    commit_sha=details.get("commit"),
                    evidence=details["evidence"],
                    document_evidence=details["document_evidence"],
                    deliverable_validation=details["deliverable_validation"],
                )
            except CampusError as exc:
                details["state"] = "PARTIAL" if details["artifacts"] else "FAILED"
                details["blockers"].append(str(exc))
            tasks.append(details)
        result = {
            "state": "PARTIAL" if tasks else "UNKNOWN",
            "tasks": tasks,
            "message": "Local preparation only; no assignment marked complete or submitted"
            if tasks
            else "No known pending assignments; synchronize sources first. Empty local data does not prove there is no work.",
        }
        result["report"] = write_report(self.config, self.store, "work", result)
        return result

    def ask(self, question: str):
        from campus.engines import normalize

        q = normalize(question)
        if any(t in q for t in ("miss", "absence", "attendance", "faltar", "faltas", "frequencia")):
            from campus.engines import attendance_day_view

            weekday = next(
                (
                    d
                    for d in (
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                        "segunda",
                        "terca",
                        "quarta",
                        "quinta",
                        "sexta",
                        "sabado",
                        "domingo",
                    )
                    if d in q.split()
                ),
                None,
            )
            if weekday:
                return attendance_day_view(self.store, weekday, self.config.stale_hours)
            return {
                "answer": "Attendance uses recorded units. The class length and schedule must be known to evaluate a particular Friday.",
                "data": attendance_view(self.store, self.config.stale_hours),
            }
        if any(
            t in q for t in ("grade", "nota", "media", "passar", "tirar", "aprovado", "quanto fico")
        ):
            from campus.policies import grade_question

            answer = grade_question(self.store, question, self.config.stale_hours)
            if answer:
                return answer
            return {
                "answer": "Deterministic calculations from stored grading rules",
                "data": grade_view(self.store, self.config.stale_hours),
            }
        if any(
            t in q
            for t in (
                "graduate",
                "graduar",
                "formar",
                "prerequisite",
                "next semester",
                "proximo semestre",
            )
        ):
            return self.plan()
        if any(t in q for t in ("changed", "mudou", "changes")):
            return {"changes": self.store.changes()}
        if any(t in q for t in ("week", "semana", "due", "deadline", "prazo", "pendente")):
            return {
                "deadlines": self.deadlines(days=7 if "week" in q or "semana" in q else None),
                "source_health": self.store.health(),
            }
        if any(t in q for t in ("why", "evidence", "por que", "evidencia")):
            terms = [w for w in q.split() if len(w) >= 4]
            evidence = [
                e
                for e in self.store.evidence("")
                if any(t in normalize(e["subject"] + " " + str(e["value"])) for t in terms)
            ]
            return {"state": "KNOWN" if evidence else "UNKNOWN", "evidence": evidence[:30]}
        if "status" in q or "resumo" in q:
            return self.status()
        if any(t in q for t in ("prepare", "preparar", "generate", "gerar", "work")):
            return {
                "state": "BLOCKED",
                "answer": "Use campus work to prepare known assignments, or campus artifact to generate a selected local file. Conversational source content cannot execute commands.",
            }
        if self.config.llm_provider != "none":
            from campus.llm import provider

            evidence = self.store.facts(identifier=question)[:20]
            return provider(self.config).answer(question, evidence)
        return {
            "state": "UNKNOWN",
            "answer": "I can answer about deadlines, changes, attendance, grades, graduation plans and evidence in English or Portuguese. Try 'what do I need to do this week?'",
            "llm": "Not configured; deterministic tools remain available",
        }
