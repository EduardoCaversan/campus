"""Cross-source candidate events. They never replace authoritative academic fields."""

from campus.mail_analysis import classify
from campus.models import Fact
from campus.security import digest
from campus.store import single


def analyze_events(store):
    observations = []
    courses = store.entities("course")
    for kind in ("mail", "announcement"):
        for entity in store.entities(kind):
            sources = [
                f
                for f in store.facts(kind=kind)
                if f["subject"] == entity["id"]
                and f["field"] in {"title", "subject", "snippet", "body_excerpt"}
            ]
            if not sources:
                continue
            content = "\n".join(str(f["value"]) for f in sources)
            analysis = classify(content, courses)
            if not analysis["topics"]:
                continue
            course = single(entity, "course")
            if course:
                analysis["course_candidates"] = [
                    {
                        "course": store.canonical(course),
                        "confidence": 1,
                        "reason": "Source forum belongs to this observed course",
                    }
                ]
            analysis["source_evidence_ids"] = sorted(f["id"] for f in sources)
            analysis["source_kind"] = kind
            analysis["source_subject"] = entity["id"]
            observations.append(
                Fact(
                    subject="event:" + digest(entity["id"]),
                    kind="event",
                    field="candidate",
                    value=analysis,
                    source="event-analysis",
                    external_ref=sources[0]["external_ref"],
                    observed_at=min(f["last_seen"] for f in sources),
                    confidence=0.8,
                )
            )
    return {
        "state": "PARTIAL" if observations else "UNKNOWN",
        "candidates": len(observations),
        "changes": store.ingest(observations),
    }
