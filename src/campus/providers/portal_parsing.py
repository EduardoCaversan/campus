"""Parsers for the observed Cornélio Procópio academic views.

Only academic rows are normalized; surrounding identity tables are not persisted.
"""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from campus.engines import normalize
from campus.providers.parsing import fact

READ_LABELS = {"boletim", "disciplinas matriculadas", "historico completo", "matrizes curriculares"}
READ_PROCEDURES = {
    "boletim": "mpboletim.inicioaluno",
    "disciplinas matriculadas": "mpconfirmacaomatricula.pctelaaluno",
    "historico completo": "mphistescol.pcprocessa",
    "matrizes curriculares": "mptabcursograde.inicio",
}
CODE = re.compile(r"^[A-Z][A-Z0-9-]{2,19}$")


def decode_html(body: bytes, content_type: str) -> str:
    declared = re.search(r"charset\s*=\s*[\"']?([\w-]+)", content_type, re.I)
    if declared:
        return body.decode(declared.group(1), errors="strict")
    return body.decode("utf-8", errors="strict")


def academic_links(html: str, base: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for card in soup.select(".card-content"):
        label = normalize(card.get_text(" ", strip=True))
        if label not in READ_LABELS:
            continue
        match = re.search(
            r"document\.getElementById\(['\"]if_navega['\"]\)\.src\s*=\s*['\"]([^'\"]+)['\"]",
            card.get("onclick", ""),
        )
        if not match:
            continue
        target = urljoin(base, match.group(1))
        origin, parsed = urlsplit(base), urlsplit(target)
        if (
            parsed.scheme == "https"
            and parsed.netloc == origin.netloc
            and parsed.path.startswith(origin.path.rsplit("/", 1)[0] + "/")
            and not parsed.username
            and parsed.path.rsplit("/", 1)[-1].lower() == READ_PROCEDURES[label]
        ):
            result[label] = target
    return result


def rows(table):
    for row in table.find_all("tr"):
        if row.find_parent("table") is table:
            yield row.find_all(["td", "th"], recursive=False)


def text(cells):
    return [c.get_text(" ", strip=True) for c in cells]


def numeric(value):
    value = value.strip()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        return float(value.replace(",", "."))
    return None


def semester(html: str):
    label = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(r"Ano/Per[ií]odo:\s*(20\d{2})/([12])", label, re.I)
    return f"{match[1]}/{match[2]}" if match else None


def emit(values, subject, kind, ref, excerpt=""):
    return [
        fact(subject, kind, field, value, "portal", ref, excerpt)
        for field, value in values.items()
        if value is not None
    ]


def course_id(code, section, term):
    return f"portal:course:{code}:{term or 'unknown'}:{section or 'unknown'}"


def bulletin(html: str, ref: str):
    soup = BeautifulSoup(html, "html.parser")
    term = semester(html)
    result = []
    allowance = re.search(
        r"Limite de Faltas Previsto\s*:\s*\[\s*Aulas Presenciais Previstas\s*\]\s*\*\s*(\d+(?:,\d+)?)\s*%",
        soup.get_text(" ", strip=True),
        re.I,
    )
    minimum = 1 - float(allowance[1].replace(",", ".")) / 100 if allowance else None
    expected = {}
    for table in soup.select("table"):
        headers = None
        for cells in rows(table):
            values = text(cells)
            norm = [normalize(v) for v in values]
            if "codigo" in norm and "aulas presenciais previstas" in norm:
                headers = norm
                continue
            if not headers or len(values) != len(headers):
                continue
            row = dict(zip(headers, values, strict=True))
            code = row["codigo"]
            if not CODE.fullmatch(code):
                continue
            section = row.get("turma", "")
            subject = course_id(code, section, term)
            partial = row.get("2 media parcial", "")
            count = re.search(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]", partial)
            expected[(code, section)] = int(count[2]) if count else None
            data = {
                "code": code,
                "name": row.get("disciplina"),
                "section": section,
                "semester": term,
                "campus": row.get("campus"),
                "enrolled": True,
                "total_units": numeric(row.get("aulas presenciais previstas", "")),
                "held_units": numeric(row.get("aulas dadas presenciais", "")),
                "absences": numeric(row.get("faltas", "")),
                "attendance_unit": "class_period",
                "minimum_attendance": minimum,
                "recorded_attendance_percent": numeric(row.get("frequencia", "")),
                "grade": numeric(row.get("media final", "")),
                "academic_status": row.get("situacao"),
                "partial_grade_display": partial,
            }
            result.extend(emit(data, subject, "course", ref, " | ".join(values)))
            if minimum is not None:
                from campus.rules import AttendancePolicy

                result.extend(
                    emit(
                        {
                            "attendance_rule": allowance[0],
                            "attendance_policy": AttendancePolicy(
                                unit="class_period",
                                maximum_absence_fraction=float(allowance[1].replace(",", "."))
                                / 100,
                                minimum_attendance_fraction=minimum,
                                expression=allowance[0],
                            ).model_dump(),
                        },
                        subject,
                        "course",
                        ref,
                        allowance[0],
                    )
                )
        # Assessment tables identify the course and section in their own title.
        title = table.get_text(" ", strip=True)
        match = re.match(r"Notas\s*\(([A-Z0-9-]+)/([^()]+)\)", title)
        if not match:
            continue
        code, section = match.groups()
        assessments = []
        for cells in rows(table):
            vals = text(cells)
            if len(vals) == 4 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", vals[0]):
                assessments.append(
                    {
                        "date": vals[0],
                        "name": vals[1],
                        "weight": numeric(vals[2]),
                        "grade": numeric(vals[3]),
                    }
                )
        if assessments:
            # Relative weights are preserved; incomplete planned assessments do not create a grading rule.
            result.extend(
                emit(
                    {
                        "assessments": assessments,
                        "assessment_count_planned": expected.get((code, section)),
                    },
                    course_id(code, section, term),
                    "course",
                    ref,
                )
            )
    return result


def enrollment(html: str, ref: str, term: str | None):
    result = []
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table"):
        headers = None
        for cells in rows(table):
            vals = text(cells)
            norm = [normalize(v) for v in vals]
            if "disciplina" in norm and "nome" in norm and "chs" in norm and "cht" in norm:
                headers = norm
                continue
            if not headers or len(vals) != len(headers):
                continue
            row = dict(zip(headers, vals, strict=True))
            code = row["disciplina"]
            if not CODE.fullmatch(code):
                continue
            data = {
                "code": code,
                "name": row["nome"],
                "section": row.get("turma"),
                "semester": term,
                "campus": row.get("campus"),
                "enrolled": True,
                "delivery_mode": row.get("enquadramento"),
                "weekly_hours": numeric(row.get("chs", "")),
                "workload": numeric(row.get("cht", "")),
            }
            result.extend(
                emit(data, course_id(code, row.get("turma"), term), "course", ref, " | ".join(vals))
            )
    schedules = {}
    for table in soup.select("table"):
        active = False
        for cells in rows(table):
            vals = text(cells)
            if (
                len(vals) == 9
                and "segunda" in normalize(vals[3])
                and "inicio" == normalize(vals[1])
            ):
                active = True
                continue
            if (
                not active
                or len(vals) != 9
                or any(c.has_attr("rowspan") or c.has_attr("colspan") for c in cells)
            ):
                continue  # Unsupported merged timetable cells are not silently expanded.
            if not re.fullmatch(r"\d{2}h\d{2}", vals[1]) or not re.fullmatch(
                r"\d{2}h\d{2}", vals[2]
            ):
                continue
            for weekday, cell in enumerate(vals[3:]):
                match = re.fullmatch(r"([A-Z]{2}\d{2}[A-Z0-9]+)-([A-Z]+\d+)/([^\s]+)", cell)
                if match:
                    code, section, room = match.groups()
                    schedules.setdefault(course_id(code, section, term), []).append(
                        {
                            "day": weekday,
                            "start": vals[1].replace("h", ":"),
                            "end": vals[2].replace("h", ":"),
                            "units": 1,
                            "room": room,
                            "period_label": vals[0],
                        }
                    )
    for subject, slots in schedules.items():
        result.extend(
            emit(
                {
                    "schedule": slots,
                    "schedule_basis": "Regular enrollment timetable, Monday=0; cancellations and exceptional dates require separate evidence",
                },
                subject,
                "course",
                ref,
            )
        )
    return result


def history(html: str, ref: str):
    soup = BeautifulSoup(html, "html.parser")
    result, completed, pending = [], set(), set()
    for table in soup.select("table"):
        headers = None
        for cells in rows(table):
            vals = text(cells)
            norm = [normalize(v) for v in vals]
            if "cod" in norm and "disciplina" in norm and "ano" in norm:
                headers = norm
                continue
            if norm == ["semestre na matriz", "codigo", "disciplina"]:
                headers = norm
                continue
            if not headers or len(vals) != len(headers):
                continue
            row = dict(zip(headers, vals, strict=True))
            code = row.get("cod", row.get("codigo", ""))
            if not CODE.fullmatch(code):
                continue
            if "semestre na matriz" in row:
                pending.add(code)
                result.extend(
                    emit(
                        {"code": code, "name": row["disciplina"], "completed": False},
                        f"portal:requirement:{code}",
                        "requirement",
                        ref,
                        " | ".join(vals),
                    )
                )
                continue
            status = next((v for k, v in row.items() if k.startswith("situacao")), "")
            normalized_status = normalize(status)
            passed = normalized_status.startswith(
                ("aprovado", "credito consignado", "dispensado")
            ) or normalized_status.startswith("enade estudante dispensado")
            if passed:
                completed.add(code)
            year = row.get("ano", "unknown")
            period = next((v for k, v in row.items() if k.startswith("semestre")), "unknown")
            section = row.get("turma") or "none"
            result.extend(
                emit(
                    {
                        "code": code,
                        "name": row["disciplina"],
                        "semester": f"{year}/{period}",
                        "section": row.get("turma"),
                        "completed": passed,
                        "academic_status": status,
                        "grade": numeric(row.get("media", "")),
                        "workload": numeric(
                            next((v for k, v in row.items() if k.startswith("cht")), "")
                        ),
                    },
                    f"portal:history:{code}:{year}:{period}:{section}",
                    "history",
                    ref,
                    " | ".join(vals),
                )
            )
    # A later successful attempt takes precedence over an earlier failure, not a silent source preference.
    result.extend(history_requirements(html, ref))
    return result, completed, pending


def history_requirements(html, ref):
    from campus.rules import CurriculumRequirement

    result = []
    for table in BeautifulSoup(html, "html.parser").select("table"):
        workload_header = False
        equivalence_header = False
        elective_header = False
        extension_header = False
        for cells in rows(table):
            if any(c.find("table") for c in cells):
                continue
            vals = text(cells)
            norm = [normalize(v) for v in vals]
            if norm == [
                "optativa",
                "nome do conjunto",
                "periodo inicial",
                "periodo final",
                "chs",
                "ch obrigatoria",
                "ch cursada e aprovada",
                "ch faltante",
                "ch validada",
            ]:
                elective_header = True
                continue
            if norm == ["", "chext f", "cursada g", "faltante h", "situacao i"]:
                extension_header = True
                continue
            if elective_header and len(vals) == 9 and vals[0].isdigit():
                rule = {
                    "type": "elective_group",
                    "group": vals[0],
                    "name": vals[1],
                    "initial_period": numeric(vals[2]),
                    "final_period": numeric(vals[3]),
                    "required_hours": numeric(vals[5]),
                    "approved_hours": numeric(vals[6]),
                    "remaining_to_approve_hours": numeric(vals[7]),
                    "validated_hours": numeric(vals[8]),
                    "status": "CONFIRMED",
                    "interpretation": "Group approval balance is distinct from curriculum validation; do not substitute it for the overall elective balance",
                }
                result.extend(
                    emit(
                        {"policy": rule},
                        f"portal:requirement:elective:{vals[0]}",
                        "requirement",
                        ref,
                        " | ".join(vals),
                    )
                )
            if extension_header and len(vals) == 5 and norm[0].startswith("chext "):
                rule = CurriculumRequirement(
                    type="extension_hours",
                    scope=vals[0],
                    required_hours=numeric(vals[1]),
                    attempted_hours=numeric(vals[2]),
                    remaining_hours=numeric(vals[3]),
                    interpretation="Explicit extension-hour balance; may overlap course workload, never add these hours to total curriculum workload automatically",
                )
                result.extend(
                    emit(
                        {"policy": {**rule.model_dump(), "source_status": vals[4]}},
                        "portal:requirement:extension:" + normalize(vals[0]).replace(" ", "-"),
                        "requirement",
                        ref,
                        " | ".join(vals),
                    )
                )
            if len(vals) == 6 and norm[:2] == ["cht", "total do curso a"] and "faltante d" in norm:
                workload_header = True
                continue
            if norm == ["disciplina equivalente", "", "disciplina obrigatoria"]:
                equivalence_header = True
                continue
            if workload_header and len(vals) == 6 and norm[0].startswith("cht "):
                scope = {
                    "cht disciplinas obrigatorias": "mandatory",
                    "cht disciplinas optativas": "elective",
                    "cht geral do curso": "overall",
                }.get(norm[0])
                if not scope:
                    continue
                values = []
                for v in vals[1:]:
                    match = re.match(r"\d+(?:\.\d{3})*(?:,\d+)?", v)
                    values.append(
                        float(match[0].replace(".", "").replace(",", ".")) if match else None
                    )
                rule = CurriculumRequirement(
                    type="workload",
                    scope=scope,
                    **dict(
                        zip(
                            (
                                "required_hours",
                                "attempted_hours",
                                "validated_hours",
                                "remaining_hours",
                                "approved_hours",
                            ),
                            values,
                            strict=True,
                        )
                    ),
                    interpretation="Explicit history columns A/B/C/D/E. Approved hours are not necessarily validated toward the curriculum; use column C and the explicit remaining balance D.",
                )
                result.extend(
                    emit(
                        {"policy": rule.model_dump()},
                        f"portal:requirement:workload:{scope}",
                        "requirement",
                        ref,
                        " | ".join(vals),
                    )
                )
            if (
                equivalence_header
                and len(vals) == 17
                and vals[10] == "=>"
                and CODE.fullmatch(vals[0])
                and CODE.fullmatch(vals[12])
            ):
                result.extend(
                    emit(
                        {
                            "rule": {
                                "source_course": vals[0],
                                "target_course": vals[12],
                                "credited": normalize(vals[16]) == "sim"
                                if normalize(vals[16]) in {"sim", "nao"}
                                else None,
                                "source_status": vals[9],
                                "source_term": vals[8],
                                "scope": "This student's recorded credit decision, not a universal automatic equivalence",
                            }
                        },
                        f"portal:equivalence:{vals[0]}:{vals[12]}:{vals[8]}",
                        "equivalence",
                        ref,
                        " | ".join(vals),
                    )
                )
    return result


def curriculum(html: str, ref: str, completed: set, pending: set, enrolled: set):
    soup = BeautifulSoup(html, "html.parser")
    result, seen = [], set()
    matrix = re.search(r"Matriz\s*:\s*(\d+)", soup.get_text(" ", strip=True))
    matrix_id = matrix[1] if matrix else "unknown"
    for table in soup.select("table"):
        active = False
        for cells in rows(table):
            vals = text(cells)
            norm = [normalize(v) for v in vals]
            if "codigo" in norm and "carga horaria total" in norm and "pre requisito s" in norm:
                active = True
                continue
            if not active or len(vals) < 15 or not vals[0].isdigit():
                continue
            code = vals[2].split()[0] if vals[2] else ""
            if not CODE.fullmatch(code) or code in seen:
                continue
            seen.add(code)
            expression = vals[14]
            prereqs = re.findall(r"\b[A-Z]{2,}\d{2,}[A-Z0-9]*\b", expression)
            remainder = expression
            for p in prereqs:
                remainder = remainder.replace(p, "")
            # Empty cells explicitly mean no prerequisites. Non-code rules and alternatives stay unknown.
            known = not normalize(remainder) or normalize(remainder) == "e"
            workload = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*horas?", vals[13], re.I)
            complete = (
                True
                if code in completed
                else False
                if code in pending or code in enrolled
                else None
            )
            data = {
                "code": code,
                "name": vals[3],
                "matrix": matrix_id,
                "curriculum_period": int(vals[0]),
                "category": vals[4],
                "optional_group": vals[1] or None,
                "workload": numeric(workload[1]) if workload else None,
                "prerequisites": sorted(set(prereqs)) if known else None,
                "prerequisite_expression": expression,
                "eligibility_constraint": {
                    "type": "period_gate",
                    "expression": expression,
                    "operator": "UNKNOWN",
                    "status": "UNRESOLVED",
                }
                if re.search(r"per[ií]odo", expression, re.I)
                else None,
                "equivalent_course_candidates": sorted(
                    set(re.findall(r"\b[A-Z]{2,}\d{2,}[A-Z0-9]*\b", vals[15]))
                )
                if len(vals) > 15
                else None,
                "completed": complete,
                "currently_enrolled": code in enrolled,
                "completion_basis": "Approved/credited history"
                if complete
                else "Explicit missing-course list or current enrollment"
                if complete is False
                else "UNKNOWN",
            }
            # Completion is derived from another view; retain its provenance separately in the provider.
            result.extend(
                emit(
                    data,
                    f"portal:curriculum:{matrix_id}:{code}",
                    "curriculum",
                    ref,
                    " | ".join(vals[:15]),
                )
            )
    return result


def parse_bundle(pages: dict[str, tuple[str, str]]):
    results = []
    term = semester(pages["boletim"][0]) if "boletim" in pages else None
    if "boletim" in pages:
        results.extend(bulletin(*pages["boletim"]))
    if "disciplinas matriculadas" in pages:
        results.extend(enrollment(*pages["disciplinas matriculadas"], term))
    completed, pending = set(), set()
    if "historico completo" in pages:
        observations, completed, pending = history(*pages["historico completo"])
        results.extend(observations)
    enrolled = {f.value for f in results if f.kind == "course" and f.field == "code"}
    if "matrizes curriculares" in pages:
        records = curriculum(*pages["matrizes curriculares"], completed, pending, enrolled)
        history_ref = pages.get("historico completo", (None, None))[1]
        for record in records:
            if record.field in {"completed", "completion_basis"} and history_ref:
                record.external_ref = history_ref
                record.excerpt = "Derived from explicit approved/credited history or missing-course list; current enrollment is not completion."
        results.extend(records)
    return results
