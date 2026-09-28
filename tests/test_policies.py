from decimal import Decimal

import pytest

from campus.models import CampusError
from campus.policies import (
    affine,
    analyze_policies,
    apply_recovery,
    grade_question,
    parse_policy,
    policy_grade,
)
from campus.providers.parsing import fact


@pytest.mark.parametrize(
    "expression,weights,constant",
    [
        ("P1 * 0.25 + P2 * 0.75", {"P1": Decimal(".25"), "P2": Decimal(".75")}, Decimal(0)),
        (
            "(A + B + C) / 3",
            {"A": Decimal(1) / 3, "B": Decimal(1) / 3, "C": Decimal(1) / 3},
            Decimal(0),
        ),
        ("A + B + 1", {"A": Decimal(1), "B": Decimal(1)}, Decimal(1)),
    ],
)
def test_affine_formulas(expression, weights, constant):
    assert affine(expression) == (weights, constant)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('bad')",
        "P1 ** 999999",
        "A * B",
        "A / B",
        "A / 0",
        "P1[0]",
        "True",
        "float('nan')",
    ],
)
def test_formula_is_not_executable_code(expression):
    with pytest.raises(CampusError):
        affine(expression)


def test_weighted_policy_and_nested_average():
    policy = parse_policy(
        "MP = (P1 + P2) / 2\nMF = MP * 0,8 + T * 0,2\nNOTA FINAL >= 5\nNotas de 0 a 10"
    )
    assert policy.state == "KNOWN"
    assert {k: Decimal(v) for k, v in policy.coefficients.items()} == {
        "P1": Decimal(".4"),
        "P2": Decimal(".4"),
        "T": Decimal(".2"),
    }
    assert policy.passing_grade == "5" and policy.scale == "10"


def test_prose_percentages_preserve_source_labels():
    policy = parse_policy(
        "Procedimentos de Avaliação\nPROJETO 1 - exemplo (25% da\nnota final); PROJETO 2 - exemplo (25% da nota final); e PROVA PRESENCIAL (50% da nota final)."
    )
    assert policy.coefficients == {
        "PROJETO_1": "0.25",
        "PROJETO_2": "0.25",
        "PROVA_PRESENCIAL": "0.5",
    }
    assert policy.passing_grade is None
    assert policy.state == "PARTIAL"


def test_ambiguous_formula_and_scale_never_fixed_silently():
    policy = parse_policy("(P1 * 0,25) + (P2 * 0,75) = 10,0\nNOTA FINAL >= 0,50 APROVADO")
    assert policy.passing_grade == "0.50"
    assert any("inconsistent units" in issue for issue in policy.unresolved)
    duplicate = parse_policy("MF = P1\nMF = P2")
    assert duplicate.state == "CONFLICT"


def test_nonweighted_sum_and_recovery_preserved():
    policy = parse_policy(
        "MF = A + B\nNotas de 0 a 10\nNOTA FINAL >= 5\nA recuperação substituirá a menor nota somente se for superior.\nArredondamento não será realizado."
    )
    assert policy.coefficients == {"A": "1", "B": "1"}
    assert any("somente se for superior" in r for r in policy.recovery_rules)
    assert policy.rounding_rules


def seed_policy(store):
    store.ingest(
        [
            fact(
                "document:example",
                "document",
                "text",
                "MF = P1 * 0.25 + P2 * 0.75\nNOTA FINAL >= 5\nNotas de 0 a 10",
                "moodle",
                "https://moodle.example/plan.pdf",
            ),
            fact(
                "document:example",
                "document",
                "course",
                "course:AB12X",
                "moodle",
                "https://moodle.example/plan.pdf",
            ),
            fact(
                "document:example",
                "document",
                "purpose",
                "teaching_policy_candidate",
                "moodle",
                "https://moodle.example/plan.pdf",
            ),
            fact("course:AB12X", "course", "code", "AB12X", "portal", "portal:1"),
            fact("course:AB12X", "course", "name", "Fictional Course", "portal", "portal:1"),
            fact(
                "course:AB12X",
                "course",
                "assessments",
                [{"name": "P1", "grade": 8}],
                "portal",
                "portal:1",
            ),
        ]
    )
    return analyze_policies(store)


def test_policy_provenance_idempotence_and_automatic_target(store):
    assert seed_policy(store)["changes"] == 1
    assert analyze_policies(store)["changes"] == 0
    result = policy_grade(store, "AB12X", target_component="P2")[0]
    assert result["required_grade"] == 4
    assert result["final_grade"] is None
    assert result["policy_evidence"]
    assert result["missing_components"] == ["P2"]
    answer = grade_question(store, "quanto preciso tirar na P2 de AB12X?")
    assert answer["data"][0]["required_grade"] == 4
    hypothetical = grade_question(store, "se eu tirar 6 na P2 de AB12X com quanto fico?")
    assert hypothetical["data"][0]["final_grade"] == 6.5
    assert hypothetical["data"][0]["scenario"]


def test_missing_policy_and_cross_source_conflict(store):
    seed_policy(store)
    store.ingest(
        [
            fact(
                "course:AB12X",
                "course",
                "grading_policy",
                parse_policy("MF = P1").model_dump(),
                "policy",
                "https://moodle.example/other.pdf",
            )
        ]
    )
    assert policy_grade(store, "AB12X")[0]["state"] == "CONFLICT"


def test_grade_never_matches_ambiguous_assessment_names(store):
    seed_policy(store)
    store.ingest(
        [
            fact(
                "course:AB12X",
                "course",
                "assessments",
                [{"name": "P1", "grade": 8}, {"name": "P1", "grade": 7}],
                "portal",
                "portal:1",
            )
        ]
    )
    assert policy_grade(store, "AB12X")[0]["state"] == "CONFLICT"


def test_recovery_replace_lowest_only_if_higher():
    policy = parse_policy(
        "MF = (P1+P2)/2\nNotas de 0 a 10\nNOTA FINAL >= 5\nA nota do exame substituirá a menor nota entre a Prova 1 e a Prova 2, desde que seja superior."
    ).model_dump()
    assert len(policy["recovery_operations"]) == 1
    original = {"P1": Decimal(4), "P2": Decimal(8)}
    updated, result = apply_recovery(policy, original, 7)
    assert updated == {"P1": Decimal(7), "P2": Decimal(8)}
    assert result["target"] == "P1" and original["P1"] == 4
    unchanged, result = apply_recovery(policy, original, 2)
    assert unchanged == original and not result["changed"]


def test_recovery_conflicting_targets_and_unknown_grades_are_blocked():
    policy = parse_policy(
        "MF = (P1+P2)/2\nO exame substituirá exclusivamente a nota da Prova 1.\nO exame substituirá exclusivamente a nota da Prova 2."
    ).model_dump()
    with pytest.raises(CampusError):
        apply_recovery(policy, {"P1": Decimal(4), "P2": Decimal(8)}, 7)
    policy["recovery_operations"] = policy["recovery_operations"][:1]
    with pytest.raises(CampusError):
        apply_recovery(policy, {}, 7)


def test_document_revision_updates_one_current_policy_and_keeps_history(store):
    seed_policy(store)
    stable = "https://moodle.example/mod/resource/view.php?id=42"
    store.ingest(
        [
            fact(
                "document:example",
                "document",
                "resource_ref",
                stable,
                "moodle",
                "https://moodle.example/plan.pdf",
            )
        ]
    )
    analyze_policies(store)
    assert len(store.entities("course", "AB12X")[0]["fields"]["grading_policy"]) == 1
    store.ingest(
        [
            fact(
                "document:revision",
                "document",
                "text",
                "MF = P1 * 0.5 + P2 * 0.5\nNOTA FINAL >= 5\nNotas de 0 a 10",
                "moodle",
                "https://moodle.example/plan-v2.pdf",
            ),
            fact(
                "document:revision",
                "document",
                "course",
                "course:AB12X",
                "moodle",
                "https://moodle.example/plan-v2.pdf",
            ),
            fact(
                "document:revision",
                "document",
                "purpose",
                "teaching_policy_candidate",
                "moodle",
                "https://moodle.example/plan-v2.pdf",
            ),
            fact(
                "document:revision",
                "document",
                "resource_ref",
                stable,
                "moodle",
                "https://moodle.example/plan-v2.pdf",
            ),
        ]
    )
    analyze_policies(store)
    policies = store.entities("course", "AB12X")[0]["fields"]["grading_policy"]
    assert len(policies) == 1 and policies[0]["coefficients"]["P1"] == "0.5"
    assert len([e for e in store.evidence("AB12X") if e["field"] == "grading_policy"]) == 3
    assert analyze_policies(store)["changes"] == 0


def test_threshold_scale_check_applies_after_explicit_scale_parsing():
    policy = parse_policy("MF = P1\nNOTA FINAL >= 0,50\nNotas de 0 a 10")
    assert policy.state == "PARTIAL"
    assert any("inconsistent units" in issue for issue in policy.unresolved)
    assert parse_policy("MF = P1\nNOTA FINAL >= 12\nNotas de 0 a 10").state == "CONFLICT"


@pytest.mark.parametrize(
    "text", ["MP = (P1+P2)/2\nMF = max(MP, REC)", "MP = (P1+P2)/2", "MP = sqrt(P1)\nMF = MP + T"]
)
def test_intermediate_formula_never_substitutes_for_unsupported_final(text):
    assert parse_policy(text).coefficients == {}


def test_independent_final_formulas_conflict():
    assert parse_policy("NF = P1\nMF = P2").state == "CONFLICT"


def test_negated_recovery_is_not_executable():
    policy = parse_policy("MF = P1\nO exame não substituirá a nota da Prova 1.")
    assert policy.recovery_operations == []
    assert policy.recovery_rules
    wrapped = parse_policy("MF = P1\nO exame não\nsubstituirá a nota da Prova 1.")
    assert wrapped.recovery_operations == []


def test_conflicting_assessment_sources_do_not_become_only_missing_data(store):
    seed_policy(store)
    store.ingest(
        [
            fact(
                "course:AB12X",
                "course",
                "assessments",
                [{"name": "P1", "grade": 5}],
                "moodle",
                "moodle:grade:1",
            )
        ]
    )
    result = policy_grade(store, "AB12X", target_component="P2")[0]
    assert result["state"] == "CONFLICT" and result["conflicting_assessment_sources"]
    assert result["required_grade"] is None
