from campus.artifacts import generate_document
from campus.deliverables import extract_requirements, validate_requirements
from campus.events import analyze_events
from campus.providers.parsing import fact
from campus.providers.portal_parsing import history_requirements


def html_table(rows):
    return (
        "<table>"
        + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows)
        + "</table>"
    )


def test_portal_workload_columns_do_not_confuse_approved_and_validated():
    facts = history_requirements(
        html_table(
            [
                [
                    "CHT",
                    "Total do Curso (A)",
                    "Cursada (B)",
                    "Cursada e Aprovada / Validada (C)",
                    "Faltante (D)",
                    "Total Cursada e Aprovada pelo Aluno (E)",
                ],
                ["CHT Disciplinas Optativas", "120", "40", "0", "120", "40"],
                [
                    "CHT Geral do curso",
                    "2.400 (Total de Créditos: 0)",
                    "1.100",
                    "1.000",
                    "1.400",
                    "1.040",
                ],
            ]
        ),
        "portal:history",
    )
    assert facts[0].value["validated_hours"] == 0
    assert facts[0].value["approved_hours"] == 40
    assert facts[0].value["remaining_hours"] == 120
    assert facts[1].value["required_hours"] == 2400
    assert all(f.external_ref == "portal:history" and f.excerpt for f in facts)


def test_individual_equivalence_is_not_automatic_credit():
    facts = history_requirements(
        html_table(
            [
                ["Disciplina Equivalente", "", "Disciplina Obrigatória"],
                [
                    "XY12A",
                    "Example",
                    "S1",
                    "R",
                    "2",
                    "30",
                    "4",
                    "100",
                    "2026/1",
                    "Reprovado Por Nota",
                    "=>",
                    "2",
                    "AB12C",
                    "Target",
                    "2",
                    "30",
                    "Não",
                ],
            ]
        ),
        "portal:history",
    )
    assert len(facts) == 1
    assert facts[0].value["credited"] is False
    assert facts[0].value["target_course"] == "AB12C"


def test_elective_and_extension_requirements_preserve_distinct_balances():
    html = html_table(
        [
            [
                "Optativa",
                "Nome do Conjunto",
                "Período inicial",
                "Período final",
                "CHS",
                "CH Obrigatória",
                "CH Cursada e Aprovada",
                "CH Faltante",
                "CH Validada",
            ],
            ["42", "Example electives", "4", "8", "8", "120", "40", "80", "0"],
        ]
    ) + html_table(
        [
            ["#", "CHEXT (F)", "Cursada (G)", "Faltante (H)", "Situação (I)"],
            ["CHEXT geral do curso", "200", "30", "170", "Falta cumprir"],
        ]
    )
    facts = history_requirements(html, "portal:history")
    assert facts[0].value["remaining_to_approve_hours"] == 80
    assert facts[0].value["validated_hours"] == 0
    assert facts[1].value["remaining_hours"] == 170


def test_deliverable_requirements_are_not_commands_or_completion(tmp_path):
    requirements = extract_requirements(
        "Entregar código fonte ZIP e relatório PDF.\nEnviar screenshot e link do repositório.\nTXT é opcional.\nEnviar PDF nomeado report.pdf.",
        [12],
    )
    assert {r["format"] for r in requirements} == {
        "zip",
        "pdf",
        "screenshot",
        "repository_url",
        "txt",
    }
    assert next(r for r in requirements if r["format"] == "txt")["state"] == "CANDIDATE"
    artifact = generate_document("Example report", tmp_path / "report.pdf")
    result = validate_requirements(requirements, [artifact])
    assert result["state"] == "PARTIAL" and result["missing"] >= 3
    assert any(r["naming_validation"] == "MATCH" for r in result["requirements"])
    assert all(not r["content_approved"] for r in result["requirements"])


def test_preparation_checklist_cannot_satisfy_requested_markdown(tmp_path):
    requirements = extract_requirements("Entregar relatório Markdown", [1])
    artifact = {
        **generate_document("Checklist only", tmp_path / "preparation.md"),
        "role": "preparation",
    }
    assert validate_requirements(requirements, [artifact])["missing"] == 1


def test_announcement_and_mail_candidates_keep_separate_evidence(store):
    store.ingest(
        [
            fact("course:1", "course", "code", "AB12X", "portal", "portal:1"),
            fact(
                "announcement:1",
                "announcement",
                "title",
                "Prazo de entrega 03/11/2026",
                "moodle",
                "moodle:forum:1",
            ),
            fact(
                "announcement:1", "announcement", "course", "course:1", "moodle", "moodle:forum:1"
            ),
            fact(
                "mail:1", "mail", "snippet", "AB12X prazo de entrega 04/11/2026", "mail", "mail:1"
            ),
        ]
    )
    assert analyze_events(store)["changes"] == 2
    assert analyze_events(store)["changes"] == 0
    candidates = store.facts(kind="event")
    assert len(candidates) == 2
    assert all(f["value"]["source_evidence_ids"] for f in candidates)
    assert store.facts(kind="assignment") == []
