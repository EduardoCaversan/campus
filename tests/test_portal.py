import pytest

from campus.engines import plan_known_curriculum
from campus.providers.portal_parsing import (
    academic_links,
    bulletin,
    curriculum,
    decode_html,
    enrollment,
    history,
)

BASE = "https://sistemas2.utfpr.edu.br/dpls/sistema/aluno02/mpmenu.inicio"


def table(headers, values):
    return (
        "<table><tr>"
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr>"
        + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in values)
        + "</table>"
    )


def test_only_observed_read_procedures_are_allowed():
    template = "<div class=\"card-content\" onclick=\"document.getElementById('if_navega').src='{}';\">Boletim</div>"
    assert academic_links(template.format("mpboletim.inicioAluno?p_curscodnr=1"), BASE)
    assert not academic_links(
        template.format("https://attacker.invalid/mpboletim.inicioAluno"), BASE
    )
    assert not academic_links(template.format("mpdangerous.pcGrava"), BASE)


def test_declared_legacy_encoding():
    original = "Situação, frequência e pré-requisitos"
    assert decode_html(original.encode("iso-8859-1"), "text/html;charset=iso-8859-1") == original
    with pytest.raises(UnicodeDecodeError):
        decode_html(b"\xff", "text/html;charset=utf-8")


def test_bulletin_units_and_rule_come_from_explicit_source():
    html = "Ano/Período: 2026/2" + table(
        [
            "Campus",
            "Código",
            "Disciplina",
            "Turma",
            "Aulas Presenciais Previstas",
            "Aulas Dadas Presenciais",
            "Faltas",
            "Média Final",
            "Situação",
        ],
        [["Example", "AA101", "Synthetic Course", "A1", "72", "20", "2", "*", "Cursando"]],
    )
    data = {f.field: f.value for f in bulletin(html, BASE)}
    assert "minimum_attendance" not in data
    assert "grade" not in data
    html += "Limite de Faltas Previsto : [ Aulas Presenciais Previstas] * 25%"
    data = {f.field: f.value for f in bulletin(html, BASE)}
    assert data["total_units"] == 72
    assert data["minimum_attendance"] == 0.75
    assert data["semester"] == "2026/2"


def test_enrollment_hours_are_not_attendance_periods():
    html = table(
        ["Campus", "Disciplina", "Nome", "Turma", "CHS", "CHT"],
        [["Example", "AA101", "Synthetic Course", "A1", "4", "60"]],
    )
    facts = enrollment(html, BASE, "2026/2")
    assert {f.field: f.value for f in facts}["workload"] == 60
    assert not any(f.field == "total_units" for f in facts)


def test_history_preserves_attempts_and_later_credit():
    html = table(
        [
            "Cód.",
            "Disciplina",
            "Turma",
            "CHT (3)",
            "Média",
            "Semestre(6)",
            "Ano",
            "Situação/Professores",
        ],
        [
            ["AA101", "Synthetic Course", "A1", "60", "3,0", "1", "2025", "Reprovado Por Nota"],
            ["AA101", "Synthetic Course", "A2", "60", "8,0", "2", "2025", "Aprovado Por Nota"],
        ],
    ) + table(["Semestre na Matriz", "Código", "Disciplina"], [["4", "AA102", "Pending Course"]])
    facts, completed, pending = history(html, BASE)
    assert completed == {"AA101"}
    assert pending == {"AA102"}
    assert len({f.subject for f in facts if f.kind == "history"}) == 2


def test_curriculum_unknown_period_gate_not_treated_as_no_prerequisite():
    headers = [
        "Período",
        "[OPT]",
        "Código",
        "Disciplina",
        "Modelo de disciplina",
        "AT",
        "AP",
        "AS",
        "APS",
        "APCC",
        "AD",
        "CHEXT",
        "CHEAD",
        "Carga horária total",
        "Pré-requisito(s)",
        "Equivalentes",
    ]
    row = [
        "6",
        "",
        "AA102 Turmas",
        "Synthetic Course",
        "NÚCLEO COMUM",
        "2",
        "2",
        "4",
        "0",
        "0",
        "0",
        "0",
        "0",
        "60 horas",
        "Período:6",
        "",
    ]
    facts = curriculum("Matriz: 999 " + table(headers, [row]), BASE, set(), {"AA102"}, set())
    values = {f.field: f.value for f in facts}
    assert values["completed"] is False
    assert "prerequisites" not in values
    assert values["prerequisite_expression"] == "Período:6"


def test_partial_planner_propagates_unknown_blockers():
    courses = [
        {"code": "A", "completed": True, "prerequisites": None, "workload": 60},
        {"code": "B", "completed": False, "prerequisites": [], "workload": 60},
        {
            "code": "C",
            "completed": False,
            "prerequisites": None,
            "workload": 60,
            "prerequisite_expression": "Period gate",
        },
        {"code": "D", "completed": False, "prerequisites": ["C"], "workload": 60},
        {
            "code": "E",
            "completed": None,
            "prerequisites": [],
            "workload": 60,
            "optional_group": "OPT",
        },
    ]
    result = plan_known_curriculum(courses)
    assert result["state"] == "PARTIAL"
    assert result["semesters"][0]["courses"] == ["B"]
    assert {c["code"] for c in result["unresolved_courses"]} == {"C", "D"}
    assert result["graduation_date"] is None
