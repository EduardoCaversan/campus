"""Deterministic academic message classification; candidates are never confirmed deadlines."""

import re

from campus.engines import normalize
from campus.models import Fact
from campus.security import digest

TOPICS = {
    "DEADLINE_CANDIDATE": r"\b(prazo|entrega|deadline|prorrogad[ao]|adiad[ao])\b",
    "EXAM_CANDIDATE": r"\b(prova|exame|exam|avaliacao)\b",
    "CLASS_CHANGE_CANDIDATE": r"\b(cancelad[ao]|cancelamento|reposicao|suspens[ao]|mudanca de horario)\b",
    "ASSIGNMENT_CANDIDATE": r"\b(trabalho|atividade|assignment|projeto|tarefa)\b",
    "ADMINISTRATIVE_CANDIDATE": r"\b(matricula|estagio|edital|declaracao|secretaria)\b",
}


def classify(text: str, courses: list[dict]):
    normalized = " " + normalize(text) + " "
    matches = []
    for course in courses:
        fields = course["fields"]
        codes = fields.get("code", [])
        names = fields.get("name", [])
        code_match = any(" " + normalize(str(code)) + " " in normalized for code in codes)
        name_match = any(
            len(normalize(str(name))) >= 12 and " " + normalize(str(name)) + " " in normalized
            for name in names
        )
        if code_match or name_match:
            matches.append(
                {
                    "course": course["id"],
                    "confidence": 1.0 if code_match else 0.9,
                    "reason": "Explicit course code"
                    if code_match
                    else "Exact normalized course-name phrase",
                }
            )
    topics = sorted(topic for topic, pattern in TOPICS.items() if re.search(pattern, normalized))
    # Full dates are candidates only: a snippet may quote an old deadline or negate it.
    dates = sorted(set(re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)))
    return {
        "state": "PARTIAL",
        "course_candidates": sorted(matches, key=lambda x: x["course"]),
        "topics": topics,
        "date_mentions": dates,
        "warning": "Deterministic message candidates, not confirmed events or assignment deadlines; inspect the original evidence",
    }


def analyze_mail(store):
    courses = store.entities("course")
    observations = []
    count = matched = 0
    for message in store.entities("mail"):
        source = [
            f
            for f in store.facts(identifier=message["id"], kind="mail")
            if f["subject"] == message["id"] and f["source"] == "mail"
        ]
        if not source:
            continue
        text = "\n".join(
            str(f["value"]) for f in source if f["field"] in {"subject", "snippet", "body_excerpt"}
        )
        result = classify(text, courses)
        result["source_evidence_ids"] = sorted(f["id"] for f in source)
        observed_at = min(f["last_seen"] for f in source)
        observations.append(
            Fact(
                subject=message["id"],
                kind="mail",
                field="analysis",
                value=result,
                source="local-analysis",
                external_ref="local:mail-analysis:" + digest(message["id"]),
                observed_at=observed_at,
                confidence=0.9,
            )
        )
        count += 1
        matched += bool(result["course_candidates"])
    changes = store.ingest(observations)
    return {
        "state": "PARTIAL" if count else "UNKNOWN",
        "messages_analyzed": count,
        "messages_with_course_candidates": matched,
        "changes": changes,
        "message": "Source evidence retained; candidate dates never overwrite assignment deadlines",
    }
