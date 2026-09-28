"""Evidence-backed deliverable requirements, never executable assignment instructions."""

import re
from pathlib import Path
from urllib.parse import urlsplit

from campus.artifacts import file_hash, validate_artifact
from campus.engines import normalize

FORMATS = {
    "zip": r"\bzip\b",
    "pdf": r"\bpdf\b",
    "docx": r"\bdocx\b",
    "txt": r"\btxt\b",
    "markdown": r"\b(markdown|md)\b",
    "screenshot": r"\b(screenshots?|capturas? de tela|prints? da tela)\b",
    "repository_url": r"\b(?:url|link)\s+(?:do\s+)?(?:repositorio|github)\b",
}


def extract_requirements(text, evidence_ids):
    requirements = []
    statements = re.split(r"\n+|(?<=[.!?;])\s+", text)
    for statement in statements:
        n = normalize(statement)
        formats = [kind for kind, regex in FORMATS.items() if re.search(regex, n)]
        if not formats:
            continue
        required = bool(
            re.search(
                r"\b(entreg\w*|envi\w*|submet\w*|anex\w*|devera|obrigatorio|required|submit|deliver|include|incluir)\b",
                n,
            )
        )
        negative = bool(re.search(r"\b(nao|not|opcional|optional|exemplo|example)\b", n))
        for kind in formats:
            item = {
                "format": kind,
                "state": "EXPLICIT" if required and not negative else "CANDIDATE",
                "excerpt": statement.strip()[:1500],
                "evidence_ids": evidence_ids,
                "naming_pattern": None,
            }
            filename = re.search(r"[\wÀ-ÿ{}<>_-]+\.(?:zip|pdf|docx|txt|md)\b", statement, re.I)
            if filename and re.search(r"\b(nome|nomeado|denominado|named|filename)\b", n):
                item["naming_pattern"] = filename[0]
            if not any(
                r["format"] == kind and r["excerpt"] == item["excerpt"] for r in requirements
            ):
                requirements.append(item)
    return requirements


def validate_requirements(requirements, artifacts, repository_url=None):
    results = []
    for requirement in requirements:
        kind = requirement["format"]
        suffixes = {"markdown": {".md"}, "screenshot": {".png", ".jpg", ".jpeg"}}.get(
            kind, {"." + kind}
        )
        matches = []
        for artifact in artifacts:
            path = Path(artifact["path"])
            if artifact.get("role") == "preparation" or path.suffix.lower() not in suffixes:
                continue
            if (
                path.is_file()
                and validate_artifact(path)
                and file_hash(path) == artifact.get("sha256")
            ):
                matches.append(str(path))
        parsed = urlsplit(repository_url or "")
        valid_repository_url = (
            parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
        )
        present = valid_repository_url if kind == "repository_url" else bool(matches)
        pattern = requirement.get("naming_pattern")
        naming = (
            "UNKNOWN"
            if pattern and any(c in pattern for c in "{}<>")
            else "MATCH"
            if pattern and any(Path(m).name == pattern for m in matches)
            else "MISMATCH"
            if pattern and matches
            else None
        )
        results.append(
            {
                **requirement,
                "validation": "PRESENT_UNREVIEWED" if present else "MISSING",
                "files": matches,
                "naming_validation": naming,
                "content_approved": False,
            }
        )
    return {
        "state": "PARTIAL" if requirements else "UNKNOWN",
        "requirements": results,
        "missing": sum(r["validation"] == "MISSING" and r["state"] == "EXPLICIT" for r in results),
        "warning": "File presence/hash/format is not proof that its academic content meets instructions. Candidate mentions and naming placeholders need review.",
    }
