import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from campus.engines import normalize
from campus.models import Fact
from campus.security import redact, safe_url


def plain(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script,style,input,textarea,button,form,iframe"):
        element.decompose()
    return redact(soup.get_text(" ", strip=True))[:100000]


def fact(subject, kind, field, value, source, ref, excerpt="", confidence=1):
    return Fact(
        subject=subject,
        kind=kind,
        field=field,
        value=value,
        source=source,
        external_ref=safe_url(ref),
        excerpt=redact(excerpt)[:100000],
        confidence=confidence,
    )


def moodle_courses(html: str, base: str) -> list[Fact]:
    soup = BeautifulSoup(html, "html.parser")
    result, seen = [], set()
    for link in soup.select('a[href*="/course/view.php?id="]'):
        url = urljoin(base, link["href"])
        cid = parse_qs(urlsplit(url).query).get("id", [None])[0]
        name = link.get_text(" ", strip=True)
        if cid and cid not in seen and name:
            seen.add(cid)
            result.append(fact(f"moodle:course:{cid}", "course", "name", name, "moodle", url, name))
    return result


def localized_date(text: str, timezone: str) -> str | None:
    months = {
        name: index
        for index, name in enumerate(
            ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"), 1
        )
    }
    match = re.search(
        r"\b(\d{1,2})\s+(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?\s+(\d{4}),?\s+(\d{2}):(\d{2})\b",
        text.lower(),
    )
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    try:
        parsed = datetime(
            int(year), months[month], int(day), int(hour), int(minute), tzinfo=ZoneInfo(timezone)
        )
        return parsed.isoformat()
    except ValueError:
        return None


def moodle_assignment(html: str, url: str, course: str, timezone="America/Sao_Paulo") -> list[Fact]:
    soup = BeautifulSoup(html, "html.parser")
    # Relative countdowns change on every read but are not academic changes.
    for row in soup.select(".submissionstatustable tr"):
        label = row.select_one("th,td")
        if label and normalize(label.get_text(" ", strip=True)) in {
            "tempo restante",
            "time remaining",
        }:
            row.decompose()
    aid = parse_qs(urlsplit(url).query).get("id", [""])[0]
    subject = f"moodle:assignment:{aid}"
    heading = soup.select_one("h2") or soup.select_one("h1")
    result = [fact(subject, "assignment", "course", course, "moodle", url)]
    if heading:
        result.append(
            fact(subject, "assignment", "name", heading.get_text(" ", strip=True), "moodle", url)
        )
    intro = soup.select_one("#intro, .activity-description")
    if intro:
        result.append(fact(subject, "assignment", "description", plain(str(intro)), "moodle", url))
    # Only machine-readable dates are authoritative. Localized prose stays evidence.
    for node in soup.select("[data-timestamp], time[datetime]"):
        label = normalize(node.parent.get_text(" ", strip=True))
        if not any(word in label for word in ("due", "vencimento", "entrega", "prazo")):
            continue
        try:
            if node.get("data-timestamp"):
                date = datetime.fromtimestamp(int(node["data-timestamp"]), UTC).isoformat()
            else:
                parsed = datetime.fromisoformat(node["datetime"].replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    continue
                date = parsed.astimezone(UTC).isoformat()
            result.append(fact(subject, "assignment", "due_at", date, "moodle", url, label))
        except (ValueError, OverflowError, OSError):
            continue
    status = soup.select_one(".submissionstatustable")
    if status:
        result.append(
            fact(subject, "assignment", "submission_details", plain(str(status)), "moodle", url)
        )
        for row in status.select("tr"):
            cells = row.select("th,td")
            if len(cells) < 2:
                continue
            label, value = (
                normalize(cells[0].get_text(" ", strip=True)),
                normalize(cells[1].get_text(" ", strip=True)),
            )
            if label in {"status de envio", "submission status"}:
                state = (
                    "submitted"
                    if value in {"enviado para avaliacao", "submitted for grading"}
                    else "draft"
                    if "rascunho" in value or "draft" in value
                    else "not_submitted"
                    if "nenhum envio" in value or "no submissions" in value
                    else "UNKNOWN"
                )
                result.append(
                    fact(
                        subject,
                        "assignment",
                        "submission_state",
                        state,
                        "moodle",
                        url,
                        row.get_text(" ", strip=True),
                    )
                )
    if not any(f.field == "due_at" for f in result):
        dates = soup.select_one('[data-region="activity-dates"], .activity-dates')
        if dates:
            text = dates.get_text(" ", strip=True)
            for label, field in (("Vencimento:", "due_at"), ("Aberto:", "opens_at")):
                if label in text:
                    parsed = localized_date(text.split(label, 1)[1], timezone)
                    if parsed:
                        result.append(
                            fact(subject, "assignment", field, parsed, "moodle", url, text)
                        )
                        if field == "due_at":
                            result.append(
                                fact(
                                    subject,
                                    "assignment",
                                    "date_assumption",
                                    "Displayed Moodle time interpreted using configured timezone "
                                    + timezone,
                                    "moodle",
                                    url,
                                )
                            )
    attachments = sorted(
        {safe_url(urljoin(url, a["href"])) for a in soup.select('a[href*="/pluginfile.php/"]')}
    )
    if attachments:
        result.append(fact(subject, "assignment", "attachments", attachments, "moodle", url))
    result.append(
        fact(
            subject,
            "assignment",
            "instructions_snapshot",
            plain(str(soup.select_one("#region-main") or soup)),
            "moodle",
            url,
        )
    )
    return result


def portal_tables(html: str, url: str) -> list[Fact]:
    """Conservative header-based parser. Never infer units from unnamed columns."""
    soup = BeautifulSoup(html, "html.parser")
    result = []
    aliases = {
        "codigo": "code",
        "cod disciplina": "code",
        "codigo disciplina": "code",
        "disciplina": "name",
        "nome da disciplina": "name",
        "turma": "section",
        "professor": "professor",
        "docente": "professor",
        "periodo letivo": "semester",
        "nota final": "grade",
        "media final": "grade",
        "faltas": "absences",
        "carga horaria": "workload",
        "situacao": "academic_status",
    }
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        headers = [
            aliases.get(normalize(c.get_text(" ", strip=True))) for c in rows[0].select("th,td")
        ]
        if "code" not in headers or "name" not in headers:
            continue
        for row in rows[1:]:
            cells = row.select("td")
            if len(cells) != len(headers):
                continue
            values = {
                h: c.get_text(" ", strip=True) for h, c in zip(headers, cells, strict=True) if h
            }
            code = values.get("code", "")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,19}", code):
                continue
            subject = "portal:course:" + ":".join(
                [code, values.get("semester", "unknown"), values.get("section", "unknown")]
            )
            for field, value in values.items():
                if not value:
                    continue
                if field in ("grade", "absences", "workload"):
                    if not re.fullmatch(r"\d+(?:[.,]\d+)?", value):
                        continue
                    value = float(value.replace(",", "."))
                result.append(
                    fact(
                        subject,
                        "course",
                        field,
                        value,
                        "portal",
                        url,
                        row.get_text(" ", strip=True),
                        confidence=0.9,
                    )
                )
    return result


def academic_mail(sender: str, subject: str, snippet: str, course_terms=()) -> bool:
    from email.utils import parseaddr

    domain = parseaddr(sender)[1].rpartition("@")[2].lower()
    if domain == "utfpr.edu.br" or domain.endswith(".utfpr.edu.br"):
        return True
    text = " " + normalize(subject + " " + snippet) + " "
    if any(
        len(normalize(term)) >= 4 and " " + normalize(term) + " " in text for term in course_terms
    ):
        return True
    return bool(re.search(r"\b(utfpr|moodle)\b", text))
