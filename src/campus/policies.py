"""Conservative policy interpretation and deterministic, non-executable grade algebra."""

import ast
import re
import unicodedata
from decimal import Decimal

from campus.engines import freshness, normalize, number
from campus.models import CampusError, Fact
from campus.rules import GradingPolicy
from campus.store import single


def affine(expression: str) -> tuple[dict[str, Decimal], Decimal]:
    """Compile a small arithmetic grammar to coefficients, without eval or function calls."""
    if len(expression) > 2000:
        raise CampusError("Grading expression exceeds parser limit")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError):
        raise CampusError("Unsupported grading expression") from None
    if len(list(ast.walk(tree))) > 150:
        raise CampusError("Grading expression exceeds parser limit")

    def combine(a, b, factor=Decimal(1)):
        coefficients = a[0].copy()
        for key, value in b[0].items():
            coefficients[key] = coefficients.get(key, Decimal(0)) + factor * value
        return coefficients, a[1] + factor * b[1]

    def scale(a, factor):
        return {k: v * factor for k, v in a[0].items()}, a[1] * factor

    def walk(node):
        if isinstance(node, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,60}", node.id):
            return {node.id: Decimal(1)}, Decimal(0)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            raw = ast.get_source_segment(expression, node)
            value = number(raw)
            if abs(value) > 100000:
                raise CampusError("Grading constant exceeds supported range")
            return {}, value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return scale(
                walk(node.operand), Decimal(-1) if isinstance(node.op, ast.USub) else Decimal(1)
            )
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return combine(left, right)
            if isinstance(node.op, ast.Sub):
                return combine(left, right, Decimal(-1))
            if isinstance(node.op, ast.Mult) and not (left[0] and right[0]):
                return scale(left, right[1]) if not right[0] else scale(right, left[1])
            if isinstance(node.op, ast.Div) and not right[0] and right[1] != 0:
                return scale(left, Decimal(1) / right[1])
        raise CampusError("Only linear arithmetic over named grade components is supported")

    return walk(tree.body)


def parse_policy(text: str) -> GradingPolicy:
    original = unicodedata.normalize("NFKC", text)
    lines = [re.sub(r"\s+", " ", line).strip(" •●\t") for line in original.splitlines()]
    flat = " ".join(lines)
    policy = GradingPolicy()
    formulas = []
    for line in lines:
        match = re.fullmatch(r"(MF|NF|MS|MP|MD|MEDIA FINAL|NOTA FINAL)\s*=\s*(.+)", line, re.I)
        if match:
            expression = match[2].rstrip(" ,;.")
            expression = re.sub(r"(?<=\d),(?=\d)", ".", expression)
            expression = expression.replace("×", "*").replace("÷", "/")

            def named_phrase(match):
                label = match[1].strip()
                key = normalize(label).replace(" ", "_").upper()
                policy.definitions[key] = label
                return "(" + key + " *"

            expression = re.sub(r"\(([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{4,})\s*\*", named_phrase, expression)
            formulas.append((match[1].upper().replace(" ", "_"), expression, line))
        else:
            maximum = re.fullmatch(r"(\([^=]+)\s*=\s*(\d+(?:[.,]\d+)?)", line)
            if maximum and re.search(r"\b[A-Z][A-Z0-9]*\b", maximum[1]):
                expression = re.sub(r"(?<=\d),(?=\d)", ".", maximum[1].strip())
                expression = re.sub(r"\b([A-Z][A-Z0-9]*)\.(?=\s|\*)", r"\1", expression)
                formulas.append(("NF", expression, line))
                policy.scale = maximum[2].replace(",", ".")
                policy.unresolved.append(
                    "Source equation equates the component expression to a maximum; interpreted as a grade expression, not a recorded grade"
                )
    compiled = {}
    declared = {output for output, _, _ in formulas}
    for output, expression, excerpt in formulas:
        policy.excerpts.append(excerpt)
        try:
            coeff, constant = affine(expression)
            if output in compiled and compiled[output] != (coeff, constant):
                policy.state = "CONFLICT"
                policy.unresolved.append("Different formulas define the same output")
            compiled[output] = (coeff, constant)
        except CampusError:
            policy.unresolved.append("Unresolved formula: " + excerpt)
    if compiled:
        outputs = [
            key
            for key in ("MF", "NF", "MEDIA_FINAL", "NOTA_FINAL", "MS", "MD", "MP")
            if key in declared
        ]
        output = outputs[0]

        def expand(name, seen):
            if name in seen:
                raise CampusError("Cyclic grading definitions")
            if name not in compiled:
                raise CampusError(
                    "A declared grading expression is unsupported; no intermediate formula is substituted"
                )
            coeff, constant = compiled[name]
            result = {}
            for key, value in coeff.items():
                if key in declared:
                    nested, offset = expand(key, seen | {name})
                    constant += value * offset
                    for term, weight in nested.items():
                        result[term] = result.get(term, Decimal(0)) + value * weight
                else:
                    result[key] = result.get(key, Decimal(0)) + value
            return result, constant

        try:
            if output == "MP":
                raise CampusError(
                    "Only an intermediate mean is defined; final-grade formula is missing"
                )
            coeff, constant = expand(output, set())
            if any(v <= 0 for v in coeff.values()):
                raise CampusError("Nonpositive grade coefficients require review")
            policy.coefficients = {k: str(v) for k, v in coeff.items()}
            policy.constant = str(constant)
            policy.output = output
            policy.formula = next(e for key, e, _ in formulas if key == output)
            for alternative in ("MF", "NF", "MEDIA_FINAL", "NOTA_FINAL"):
                if (
                    alternative in declared
                    and alternative != output
                    and expand(alternative, set()) != (coeff, constant)
                ):
                    policy.state = "CONFLICT"
                    policy.unresolved.append(
                        "Independent final-grade formulas disagree; conditional interpretation is unresolved"
                    )
        except CampusError as exc:
            policy.coefficients = {}
            policy.unresolved.append(str(exc))
    # Explicit prose percentages; retain component descriptions as the only labels.
    percentages = re.findall(
        r"(?:^|;\s*(?:e\s+)?)([^;]+?)\s*\((\d+(?:[.,]\d+)?)\s*%\s+da\s+nota\s+final\)", flat, re.I
    )
    if not formulas and percentages:
        # Restrict first component to the evaluation section, not preceding timetable text.
        percent_values = []
        for label, percentage in percentages:
            label = re.split(r"Procedimentos\s+de\s+Avalia[çc][aã]o", label, flags=re.I)[-1].strip()
            if len(label) > 200:
                policy.unresolved.append("Percentage component boundary ambiguous")
                continue
            key = normalize(label.split(" - ")[0]).replace(" ", "_").upper()[:60]
            if key:
                percent_values.append((key, number(percentage.replace(",", ".")) / 100, label))
        if percent_values and sum(v for _, v, _ in percent_values) == 1:
            policy.coefficients = {k: str(v) for k, v, _ in percent_values}
            policy.definitions.update({k: label for k, _, label in percent_values})
            policy.formula = " + ".join(f"{k} * {v}" for k, v, _ in percent_values)
            policy.output = "NF"
            policy.excerpts.extend(
                label + f" ({v * 100}% da nota final)" for _, v, label in percent_values
            )
    for line in lines:
        definition = re.search(r"([\wÀ-ÿ][\wÀ-ÿ \-]+?)\s*\(([A-Z][A-Z0-9]{0,8})\)", line)
        if definition and definition[2] in policy.coefficients:
            policy.definitions[definition[2]] = definition[1].strip()
        n = normalize(line)
        if any(t in n for t in ("substitui", "recuperacao", "arredonda", "frequencia minima")):
            destination = (
                policy.rounding_rules
                if "arredonda" in n
                else policy.conditions
                if "frequencia minima" in n
                else policy.recovery_rules
            )
            if line and line not in destination:
                destination.append(line)
    # Preserve complete adjacent recovery prose, including conditions split across PDF lines.
    recovery = re.findall(
        r"[^.\n]*(?:substituir[aá]|substitui|recupera[çc][aã]o)[^.]*\.", flat, re.I
    )
    policy.recovery_rules = list(
        dict.fromkeys([*policy.recovery_rules, *[r.strip()[:1500] for r in recovery]])
    )[:20]
    # Execute only complete joined sentences; a wrapped negative clause must not
    # become a positive rule because its "não" was on the preceding PDF line.
    for sentence in recovery:
        n = normalize(sentence)
        if re.search(r"\b(nao|nunca|jamais)\b", n):
            continue  # Negative clauses are evidence, never affirmative replacement operations.
        target = re.search(r"substitui\w*.*?(?:nota (?:da|de) (?:prova|p)\s*(\d+))", n)
        lowest = re.search(r"menor nota entre (?:a )?prova\s*(\d+) e (?:a )?prova\s*(\d+)", n)
        if lowest:
            operation = {
                "type": "replace_lowest",
                "components": ["P" + lowest[1], "P" + lowest[2]],
                "only_if_higher": "superior" in n,
                "excerpt": sentence,
            }
        elif target:
            operation = {
                "type": "replace",
                "components": ["P" + target[1]],
                "only_if_higher": "superior" in n,
                "excerpt": sentence,
            }
        else:
            continue
        if not any(
            {k: v for k, v in r.items() if k != "excerpt"}
            == {k: v for k, v in operation.items() if k != "excerpt"}
            for r in policy.recovery_operations
        ):
            policy.recovery_operations.append(operation)
    if len(policy.recovery_operations) > 1:
        policy.unresolved.append(
            "Recovery replacement instructions disagree or require multiple conditional stages; no automatic recovery selection"
        )
    thresholds = re.findall(
        r"(?:NOTA FINAL|M[EÉ]DIA(?:\s+SEMESTRAL)?(?:\s*\([A-Z]+\))?)\s*(?:>=|≥|m[ií]nima\s*(?:de)?|igual ou superior a)\s*(\d+(?:[.,]\d+)?)",
        flat,
        re.I,
    )
    thresholds = sorted({v.replace(",", ".") for v in thresholds})
    if len(thresholds) == 1:
        policy.passing_grade = thresholds[0]
    elif len(thresholds) > 1:
        policy.state = "CONFLICT"
        policy.unresolved.append("Conflicting passing thresholds: " + ", ".join(thresholds))
    scale = re.search(
        r"(?:escala\s*(?:de)?|notas?\s*(?:de|entre))\s*0\s*(?:a|até|e|-)\s*(\d+(?:[.,]\d+)?)",
        flat,
        re.I,
    )
    if scale:
        policy.scale = scale[1].replace(",", ".")
    if policy.scale and policy.passing_grade:
        if number(policy.passing_grade) < 1 and number(policy.scale) > 1:
            policy.unresolved.append(
                "Passing threshold and displayed grade scale may use inconsistent units; no automatic rescaling"
            )
        if number(policy.passing_grade) > number(policy.scale):
            policy.state = "CONFLICT"
            policy.unresolved.append("Passing threshold exceeds the explicit grade scale")
    if not policy.coefficients:
        policy.unresolved.append("No unambiguous executable final-grade formula extracted")
    elif sum(number(v) for v in policy.coefficients.values()) > 1 and re.search(
        r"\bPeso\s+\d", flat, re.I
    ):
        policy.state = "CONFLICT"
        policy.unresolved.append(
            "Formula coefficients exceed one while the document also describes assessment weights; possible sum/average disagreement requires review"
        )
    if not policy.passing_grade:
        policy.unresolved.append("Passing threshold not established by this source")
    if not policy.scale:
        policy.unresolved.append("Grade scale not established by this source")
    if policy.state != "CONFLICT":
        policy.state = "PARTIAL" if policy.unresolved else "KNOWN"
    return policy


def analyze_policies(store):
    observations = []
    latest = {}
    document_sources = {
        f["subject"]: f for f in store.facts(kind="document") if f["field"] == "text"
    }
    resource_by_document = {}
    for document in store.entities("document"):
        if single(document, "purpose") != "teaching_policy_candidate":
            continue
        course, text = single(document, "course"), single(document, "text")
        if not course or not text or document["conflicts"]:
            continue
        source = document_sources[document["id"]]
        resource_ref = single(document, "resource_ref", source["external_ref"])
        resource_by_document[document["id"]] = (course, resource_ref)
        key = (course, resource_ref)
        previous = latest.get(key)
        if previous is None or (source["last_seen"], source["id"]) > (
            previous[1]["last_seen"],
            previous[1]["id"],
        ):
            latest[key] = (document, source, text)
    for (course, resource_ref), (document, source, text) in latest.items():
        policy = parse_policy(text)
        observations.append(
            Fact(
                subject=course,
                kind="course",
                field="grading_policy",
                value={
                    **policy.model_dump(),
                    "document": document["id"],
                    "source_evidence": source["id"],
                    "resource_ref": resource_ref,
                },
                source="policy",
                external_ref=resource_ref,
                observed_at=source["last_seen"],
                excerpt="\n".join(policy.excerpts),
                confidence=0.9,
            )
        )
    changes = store.ingest(observations)
    # Upgrade only derived current pointers with a proven stable resource identity.
    # Original observations, snapshots and change history remain immutable and queryable.
    with store.transaction():
        for existing in store.facts(kind="course"):
            if (
                existing["field"] != "grading_policy"
                or existing["source"] != "policy"
                or not isinstance(existing["value"], dict)
            ):
                continue
            resource = resource_by_document.get(existing["value"].get("document"))
            if resource in latest and existing["external_ref"] != resource[1]:
                store.connection.execute(
                    "DELETE FROM current WHERE evidence_id=?", (existing["id"],)
                )
    return {
        "state": "PARTIAL" if observations else "UNKNOWN",
        "policies": len(observations),
        "changes": changes,
    }


def apply_recovery(policy, values, score):
    operations = policy.get("recovery_operations", [])
    if len(operations) != 1:
        raise CampusError("Recovery needs one unambiguous source-backed replacement rule")
    rule = operations[0]
    components = rule["components"]
    if any(c not in policy["coefficients"] or c not in values for c in components):
        raise CampusError("Recovery target component grades are missing or not defined")
    score = number(score)
    if score < 0 or policy.get("scale") and score > number(policy["scale"]):
        raise CampusError("Recovery grade is outside the known scale")
    target = (
        min(components, key=lambda k: values[k])
        if rule["type"] == "replace_lowest"
        else components[0]
    )
    if (
        rule["type"] == "replace_lowest"
        and len({values[c] for c in components}) == 1
        and len({policy["coefficients"][c] for c in components}) > 1
    ):
        raise CampusError(
            "Equal lowest grades have different weights; recovery tie rule is unknown"
        )
    updated = dict(values)
    if not rule["only_if_higher"] or score > values[target]:
        updated[target] = score
    return updated, {
        "target": target,
        "changed": updated[target] != values[target],
        "assumption": "Hypothetical recovery only; eligibility and attendance approval are not established",
    }


def policy_grade(
    store, identifier="", overrides=None, target_component=None, stale_hours=24, recovery_grade=None
):
    result = []
    for course in store.entities("course", identifier):
        policies = course["fields"].get("grading_policy", [])
        if not policies:
            result.append(
                {
                    "course": course["id"],
                    "state": "UNKNOWN",
                    "missing": ["evidence-backed grading policy"],
                }
            )
            continue
        if len(policies) != 1:
            result.append(
                {
                    "course": course["id"],
                    "state": "CONFLICT",
                    "policies": policies,
                    "evidence": course["evidence"],
                }
            )
            continue
        policy = policies[0]
        assessment_conflict = "assessments" in course["conflicts"]
        coeff = {k: number(v) for k, v in policy["coefficients"].items()}
        values, matches, ambiguous = {}, {}, []
        assessments = single(course, "assessments", [])
        for key in coeff:
            aliases = {normalize(key), normalize(policy["definitions"].get(key, ""))} - {""}
            matches[key] = [
                a
                for a in assessments
                if normalize(a.get("name", "")) in aliases and a.get("grade") is not None
            ]
            if len(matches[key]) == 1:
                values[key] = number(matches[key][0]["grade"])
            elif len(matches[key]) > 1:
                ambiguous.append(key)
        for key, value in (overrides or {}).items():
            if key not in coeff:
                raise CampusError("Scenario component is not present in the selected policy")
            numeric = number(value)
            if numeric < 0 or policy.get("scale") and numeric > number(policy["scale"]):
                raise CampusError("Scenario grade is outside the known scale")
            values[key] = numeric
        recovery_result = None
        if recovery_grade is not None:
            values, recovery_result = apply_recovery(policy, values, recovery_grade)
        missing = [k for k in coeff if k not in values]
        points = number(policy["constant"]) + sum(
            (coeff[k] * v for k, v in values.items()), Decimal(0)
        )
        state = (
            "CONFLICT"
            if policy["state"] == "CONFLICT" or ambiguous or assessment_conflict
            else "UNKNOWN"
            if not coeff
            else "PARTIAL"
            if missing or policy["unresolved"]
            else "KNOWN"
        )
        row = {
            "course": course["id"],
            "state": state,
            "formula": policy["formula"],
            "known_weighted_points": float(points) if coeff else None,
            "final_grade": float(points) if coeff and not missing and state != "CONFLICT" else None,
            "components": {
                k: {"coefficient": str(v), "grade": str(values[k]) if k in values else None}
                for k, v in coeff.items()
            },
            "missing_components": missing,
            "ambiguous_assessment_matches": ambiguous,
            "conflicting_assessment_sources": assessment_conflict,
            "unresolved_rules": policy["unresolved"],
            "recovery_rules": policy["recovery_rules"],
            "recovery_operations": policy.get("recovery_operations", []),
            "rounding_rules": policy.get("rounding_rules", []),
            "approved": None,
            "grade_requirement_met": bool(points >= number(policy["passing_grade"]))
            if not missing
            and policy.get("passing_grade")
            and not policy["unresolved"]
            and state != "CONFLICT"
            else None,
            "scenario": bool(overrides) or recovery_grade is not None,
            "recovery_scenario": recovery_result,
            "policy_evidence": policy.get("source_evidence"),
            "evidence": course["evidence"],
            "freshness": freshness(course["evidence"], stale_hours),
            "assumptions": [
                "Only exact assessment names/codes are matched. Missing grades are not zero. Recovery and attendance are not inferred."
            ],
        }
        if target_component:
            if target_component not in coeff:
                row["required_grade"] = None
                row["target_blocker"] = "Requested component is not defined by this policy"
            elif (
                any(k != target_component for k in missing)
                or not policy.get("passing_grade")
                or policy["unresolved"]
                or state == "CONFLICT"
            ):
                row["required_grade"] = None
                row["target_blocker"] = (
                    "Other component grades or an unambiguous passing rule are missing"
                )
            else:
                other = points - coeff[target_component] * values.get(target_component, Decimal(0))
                row["required_grade"] = float(
                    max(
                        Decimal(0),
                        (number(policy["passing_grade"]) - other) / coeff[target_component],
                    )
                )
                row["target_component"] = target_component
        result.append(row)
    return result or [{"state": "UNKNOWN", "missing": ["Matching course"]}]


def grade_question(store, question, stale_hours=24):
    q = normalize(question)
    candidates = []
    aliases = {"mobile": "dispositivos moveis", "backend": "back end"}
    expanded = q + " " + " ".join(value for key, value in aliases.items() if key in q.split())
    for course in store.entities("course"):
        names = [str(v) for field in ("name", "code") for v in course["fields"].get(field, [])]
        if any(
            normalize(name) in expanded
            or any(
                token in expanded
                for token in ("dispositivos moveis", "back end")
                if token in normalize(name)
            )
            for name in names
        ):
            candidates.append(course)
    if len(candidates) != 1:
        return (
            {
                "state": "UNKNOWN",
                "missing": ["Unambiguous course; use its course code"],
                "candidates": [e["id"] for e in candidates],
            }
            if candidates
            else None
        )
    course = candidates[0]
    policy = single(course, "grading_policy", {})
    requested = re.search(r"\b([PT][0-9]+|PROJ|TB|AT)\b", question, re.I)
    component = requested[1].upper() if requested else None
    hypothetical = re.search(r"\b(?:tirar|nota|grade)\s+(\d+(?:[.,]\d+)?)\b", question, re.I)
    overrides = {}
    if hypothetical:
        if not component:
            return {
                "state": "UNKNOWN",
                "course": course["id"],
                "missing": [
                    "Which assessment receives the hypothetical grade; use an explicit component"
                ],
                "components": list(policy.get("coefficients", {})),
            }
        overrides[component] = hypothetical[1].replace(",", ".")
    needed = component if any(t in q for t in ("preciso", "need", "minim")) else None
    rows = policy_grade(store, course["id"], overrides, needed, stale_hours)
    return {
        "state": rows[0]["state"],
        "data": rows,
        "answer": "Deterministic course policy calculation; missing components and unresolved rules are not guessed.",
    }
