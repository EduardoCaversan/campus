import math
import re
import unicodedata
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

from campus.models import CampusError
from campus.store import Store, single


def number(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise CampusError("Expected a finite number") from None


def attendance(total=None, absences=None, minimum=None, held=None, hypothetical=0) -> dict:
    missing = [
        name
        for name, value in (
            ("total_units", total),
            ("absences", absences),
            ("minimum_attendance", minimum),
        )
        if value is None
    ]
    if missing:
        return {"state": "UNKNOWN", "missing": missing, "safe_to_miss": None}
    total, absences, minimum, hypothetical = map(number, (total, absences, minimum, hypothetical))
    if total <= 0 or absences < 0 or absences > total or not 0 <= minimum <= 1 or hypothetical < 0:
        raise CampusError(
            "Invalid attendance values: use consistent nonnegative units and a minimum fraction from 0 to 1"
        )
    maximum = (total * (1 - minimum)).to_integral_value(rounding=ROUND_FLOOR)
    remaining = None
    current = None
    if held is not None:
        held = number(held)
        if not absences <= held <= total:
            raise CampusError("Held units must be between recorded absences and total units")
        remaining = total - held
        current = float((held - absences) / held * 100) if held else None
        if hypothetical > remaining:
            raise CampusError("Hypothetical absence exceeds remaining units")
    return {
        "state": "KNOWN",
        "absence_allowance": float(maximum),
        "absences": float(absences),
        "remaining_allowance": float(maximum - absences),
        "current_attendance_percent": current,
        "remaining_units": float(remaining) if remaining is not None else None,
        "hypothetical_absences": float(hypothetical),
        "allowance_after": float(maximum - absences - hypothetical),
        "within_known_allowance": absences + hypothetical <= maximum,
        "assumptions": [
            "Total, held, absent and hypothetical values use the same unit; no unrecorded absences.",
            "This is an allowance calculation, not a guarantee of passing or permission to miss a class.",
        ],
    }


def grades(components: list[dict], target=6, scale=10) -> dict:
    if not components:
        return {"state": "UNKNOWN", "missing": ["grading components and weights"]}
    target, scale = number(target), number(scale)
    if not 0 <= target <= scale or scale <= 0:
        raise CampusError("Grade target must be between zero and the grade scale")
    weights = [number(c["weight"]) for c in components]
    if any(w <= 0 for w in weights) or sum(weights) != 1:
        return {"state": "UNKNOWN", "missing": ["complete positive weights summing to 1"]}
    earned = Decimal(0)
    future = Decimal(0)
    for item, weight in zip(components, weights, strict=True):
        if item.get("grade") is None:
            future += weight
        else:
            grade = number(item["grade"])
            if not 0 <= grade <= scale:
                raise CampusError("Grade lies outside the configured scale")
            earned += grade * weight
    required = max(Decimal(0), (target - earned) / future) if future else None
    return {
        "state": "KNOWN",
        "weighted_points": float(earned),
        "remaining_weight": float(future),
        "required_average_on_remaining": float(required) if required is not None else None,
        "attainable": earned >= target if required is None else required <= scale,
        "final_grade": float(earned) if not future else None,
        "assumptions": [
            "Weights, target and scale are explicitly supplied; no recovery-exam or rounding rule is inferred."
        ],
    }


def normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def correlate(store: Store) -> list[dict]:
    courses = store.entities("course")
    suggestions = []
    for i, left in enumerate(courses):
        for right in courses[i + 1 :]:
            lc, rc = single(left, "code"), single(right, "code")
            ln, rn = single(left, "name", ""), single(right, "name", "")
            ls, rs = single(left, "semester"), single(right, "semester")
            same_code = bool(lc and rc and normalize(lc) == normalize(rc))
            same_name = bool(ln and rn and normalize(ln) == normalize(rn))
            if ls and rs and ls != rs:
                continue
            if not same_code and not same_name:
                continue
            # Missing semester/section can join distinct offerings: require review.
            confirmed = bool(
                same_code
                and ls
                and ls == rs
                and single(left, "section") is not None
                and single(left, "section") == single(right, "section")
            )
            canonical, alias = sorted(
                [left["id"], right["id"]], key=lambda x: (not x.startswith("portal:"), x)
            )
            reason = (
                "Matching code, semester and section"
                if confirmed
                else "Matching code or exact normalized name; review semester and section"
            )
            confidence = 1.0 if confirmed else 0.8 if same_code else 0.65
            if confirmed:
                store.map(alias, canonical, confidence, reason)
            suggestions.append(
                {
                    "alias": alias,
                    "canonical": canonical,
                    "confidence": confidence,
                    "confirmed": confirmed,
                    "reason": reason,
                }
            )
    return suggestions


def plan_curriculum(courses: list[dict], max_load=360, max_terms=20, start_term=1) -> dict:
    """Prerequisites must be completed in an earlier term; no inferred co-requisites."""
    if not courses:
        return {
            "state": "UNKNOWN",
            "missing": ["curriculum, completion status, prerequisites and workload"],
        }
    if max_load <= 0 or start_term not in (1, 2):
        raise CampusError("Workload must be positive and start_term must be 1 or 2")
    by_id = {c["code"]: c for c in courses}
    if len(by_id) != len(courses):
        return {"state": "CONFLICT", "reason": "Duplicate curriculum course codes"}
    done = {c["code"] for c in courses if c.get("completed") is True}
    pending = set(by_id) - done
    invalid = [
        code
        for code in pending
        if any(by_id[code].get(k) is None for k in ("prerequisites", "workload", "completed"))
    ]
    if invalid:
        return {"state": "UNKNOWN", "missing_course_data": sorted(invalid)}
    for code in pending:
        if (
            not isinstance(by_id[code]["prerequisites"], list)
            or not isinstance(by_id[code]["workload"], (int, float))
            or not math.isfinite(by_id[code]["workload"])
            or by_id[code]["workload"] <= 0
        ):
            raise CampusError(
                "Curriculum workloads must be positive finite numbers and prerequisites must be lists"
            )
    unknown = {
        p
        for c in courses
        if c["code"] not in done
        for p in (c.get("prerequisites") or [])
        if p not in by_id and p not in done
    }
    if unknown:
        return {"state": "BLOCKED", "unknown_prerequisites": sorted(unknown)}
    visiting, visited = set(), set()

    def visit(code):
        if code in done or code in visited:
            return False
        if code in visiting:
            return True
        visiting.add(code)
        if any(visit(p) for p in by_id[code].get("prerequisites", [])):
            return True
        visiting.remove(code)
        visited.add(code)
        return False

    if any(visit(code) for code in sorted(pending)):
        return {"state": "CONFLICT", "reason": "Prerequisite cycle detected"}
    dependents = {
        code: sum(code in (c.get("prerequisites") or []) for c in courses) for code in by_id
    }
    terms = []
    for index in range(max_terms):
        if not pending:
            break
        term = (start_term - 1 + index) % 2 + 1
        eligible = [
            code
            for code in pending
            if set(by_id[code]["prerequisites"]) <= done
            and (not by_id[code].get("offerings") or term in by_id[code]["offerings"])
        ]
        chosen, load, slots = [], 0, []
        for code in sorted(eligible, key=lambda x: (-dependents[x], x)):
            c = by_id[code]
            candidate_slots = c.get("schedule", [])
            overlap = any(
                a["day"] == b["day"] and a["start"] < b["end"] and b["start"] < a["end"]
                for a in slots
                for b in candidate_slots
            )
            if load + c["workload"] <= max_load and not overlap:
                chosen.append(code)
                load += c["workload"]
                slots.extend(candidate_slots)
        terms.append(
            {
                "relative_semester": index + 1,
                "term_of_year": term,
                "courses": chosen,
                "workload": load,
                "offerings_confirmed": all(
                    by_id[c].get("offerings_confirmed") is True for c in chosen
                )
                if chosen
                else False,
            }
        )
        done.update(chosen)
        pending.difference_update(chosen)
    return {
        "state": "PARTIAL" if pending else "ESTIMATED",
        "semesters": terms,
        "remaining_blocked": sorted(pending),
        "estimated_semesters": len(terms) if not pending else None,
        "bottlenecks": sorted(dependents, key=lambda x: (-dependents[x], x))[:5],
        "assumptions": [
            "Unknown offerings are assumed available every term; historic term patterns are estimates.",
            "Current enrollment does not count as completed. Prerequisites require earlier-term completion.",
            "Greedy feasible plan, not a guaranteed shortest plan. Unknown schedules are not checked.",
            "Graduation also depends on requirements outside this supplied curriculum (internship, hours, approvals).",
        ],
    }


def plan_known_curriculum(courses: list[dict], max_load=360, start_term=1):
    """Plan the supported subset while explicitly retaining every unresolved requirement."""
    if not courses:
        return plan_curriculum(courses, max_load=max_load, start_term=start_term)
    electives, other, blocked, usable = [], [], {}, []
    for course in courses:
        code = course["code"]
        category = normalize(course.get("category", ""))
        if course.get("completed") is True:
            usable.append(course)
        elif course.get("optional_group"):
            electives.append(
                {
                    "code": code,
                    "group": course["optional_group"],
                    "state": "UNKNOWN",
                    "reason": "Elective choice and required group credits must be confirmed",
                }
            )
        elif course.get("workload") == 0 or category in {"estagio", "atividades complementares"}:
            other.append(
                {
                    "code": code,
                    "category": course.get("category"),
                    "completed": course.get("completed"),
                    "rule": course.get("prerequisite_expression"),
                    "state": "BLOCKED",
                }
            )
        elif (
            course.get("completed") is None
            or course.get("prerequisites") is None
            or course.get("workload") is None
        ):
            blocked[code] = {
                "code": code,
                "state": "UNKNOWN",
                "reason": "Completion/workload or prerequisite rule is incomplete",
                "rule": course.get("prerequisite_expression"),
            }
        else:
            usable.append(course)
    # Excluding an unknown prerequisite must also block its dependents, never make them eligible.
    while True:
        available = {c["code"] for c in usable}
        removed = [
            c
            for c in usable
            if c.get("completed") is not True
            and any(p not in available for p in c["prerequisites"])
        ]
        if not removed:
            break
        for c in removed:
            blocked[c["code"]] = {
                "code": c["code"],
                "state": "BLOCKED",
                "reason": "Depends on unresolved or excluded requirements",
                "prerequisites": c["prerequisites"],
            }
            usable.remove(c)
    result = plan_curriculum(usable, max_load=max_load, start_term=start_term)
    result.update(
        {
            "excluded_elective_options": electives,
            "non_course_requirements": other,
            "unresolved_courses": list(blocked.values()),
            "scope": "Known mandatory-course subset; this is not a confirmed graduation date",
            "graduation_date": None,
        }
    )
    if electives or other or blocked:
        result["state"] = "PARTIAL"
        result["known_course_semesters"] = result.pop("estimated_semesters", None)
    return result


def freshness(evidence: list[dict], stale_hours=24) -> dict:
    if not evidence:
        return {"state": "UNKNOWN", "oldest_observation": None}
    oldest = min(e["last_seen"] for e in evidence)
    age = max(0, (datetime.now(UTC) - datetime.fromisoformat(oldest)).total_seconds() / 3600)
    return {
        "state": "STALE" if age > stale_hours else "FRESH",
        "oldest_observation": oldest,
        "age_hours": round(age, 2),
    }


def attendance_view(store: Store, stale_hours=24, hypothetical=0):
    result = []
    for entity in store.entities("course"):
        fields = ["total_units", "absences", "minimum_attendance", "held_units"]
        conflicts = set(fields) & set(entity["conflicts"])
        calculation = (
            {"state": "CONFLICT", "fields": sorted(conflicts)}
            if conflicts
            else attendance(*(single(entity, key) for key in fields), hypothetical=hypothetical)
        )
        result.append(
            {
                "course": entity["id"],
                "name": single(entity, "name"),
                **calculation,
                "freshness": freshness(entity["evidence"], stale_hours),
                "evidence": entity["evidence"],
            }
        )
    return result or [
        {"state": "UNKNOWN", "missing": ["synchronized courses and attendance rules"]}
    ]


def grade_view(store: Store, stale_hours=24):
    result = []
    for entity in store.entities("course"):
        if entity["fields"].get("grading_policy"):
            from campus.policies import policy_grade

            result.extend(policy_grade(store, entity["id"], stale_hours=stale_hours))
            continue
        conflicts = set(entity["conflicts"]) & {"grading", "passing_grade", "grade_scale"}
        rule, target, scale = (
            single(entity, k) for k in ("grading", "passing_grade", "grade_scale")
        )
        calculation = {
            "state": "UNKNOWN",
            "missing": ["complete grading rules, passing grade and scale"],
        }
        if conflicts:
            calculation = {"state": "CONFLICT", "fields": sorted(conflicts)}
        elif rule is not None and target is not None and scale is not None:
            calculation = grades(rule, target, scale)
        result.append(
            {
                "course": entity["id"],
                "name": single(entity, "name"),
                "recorded_grade": single(entity, "grade"),
                "recorded_assessments": single(entity, "assessments", []),
                "partial_grade_display": single(entity, "partial_grade_display"),
                **calculation,
                "freshness": freshness(entity["evidence"], stale_hours),
                "evidence": entity["evidence"],
            }
        )
    return result or [{"state": "UNKNOWN", "missing": ["synchronized grades"]}]


def attendance_day_view(store: Store, day: str, stale_hours=24):
    names = [
        ("monday", "segunda"),
        ("tuesday", "terca"),
        ("wednesday", "quarta"),
        ("thursday", "quinta"),
        ("friday", "sexta"),
        ("saturday", "sabado"),
        ("sunday", "domingo"),
    ]
    key = normalize(day).removesuffix(" feira")
    weekday = next((i for i, aliases in enumerate(names) if key in aliases), None)
    if weekday is None:
        raise CampusError("Specify a weekday in English or Portuguese")
    results, unavailable = [], []
    for course in store.entities("course"):
        slots = single(course, "schedule")
        if slots is None:
            if single(course, "enrolled") is True:
                unavailable.append(course["id"])
            continue
        selected = [s for s in slots if s.get("day") == weekday]
        if not selected:
            continue
        units = sum(s.get("units", 0) for s in selected)
        required = {"total_units", "held_units", "absences", "minimum_attendance", "schedule"}
        if required & set(course["conflicts"]):
            calculation = {"state": "CONFLICT"}
        else:
            try:
                calculation = attendance(
                    single(course, "total_units"),
                    single(course, "absences"),
                    single(course, "minimum_attendance"),
                    single(course, "held_units"),
                    units,
                )
            except CampusError as exc:
                calculation = {"state": "UNKNOWN", "reason": str(exc)}
        results.append(
            {
                "course": course["id"],
                "name": single(course, "name"),
                "schedule": selected,
                **calculation,
                "freshness": freshness(course["evidence"], stale_hours),
                "evidence": course["evidence"],
            }
        )
    return {
        "state": "PARTIAL" if results else "UNKNOWN",
        "weekday": names[weekday][0],
        "courses": results,
        "courses_without_verified_schedule": unavailable,
        "safe_to_miss": None,
        "assumptions": [
            "Hypothesis: miss all listed periods on one regular occurrence of this weekday.",
            "Regular timetable only; holidays, cancellations, date-specific attendance policies and unrecorded absences are not verified.",
        ],
    }
