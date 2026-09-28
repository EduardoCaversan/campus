import pytest

from campus.engines import attendance, grades, normalize, plan_curriculum
from campus.models import CampusError


def test_attendance_allowance_and_impact():
    result = attendance(60, 12, 0.75, 40, 2)
    assert result["absence_allowance"] == 15
    assert result["allowance_after"] == 1
    assert result["remaining_units"] == 20
    assert result["current_attendance_percent"] == 70
    assert result["within_known_allowance"] is True


def test_attendance_fractional_allowance_rounds_down():
    assert attendance(62, 15, 0.75)["remaining_allowance"] == 0
    assert not attendance(62, 15, 0.75, hypothetical=1)["within_known_allowance"]


@pytest.mark.parametrize(
    "args",
    [
        (0, 0, 0.75),
        (60, -1, 0.75),
        (60, 4, 75),
        (60, 61, 0.75),
        (60, 4, 0.75, 2),
        (60, 4, 0.75, 59, 2),
        (60, float("nan"), 0.75),
    ],
)
def test_attendance_invalid(args):
    with pytest.raises(CampusError):
        attendance(*args)


def test_missing_attendance_does_not_claim_safety():
    result = attendance(60, 3)
    assert result["state"] == "UNKNOWN"
    assert result["safe_to_miss"] is None


def test_weighted_grade_required():
    result = grades([{"weight": 0.4, "grade": 5}, {"weight": 0.6, "grade": None}], 6)
    assert result["required_average_on_remaining"] == pytest.approx(6.6666666667)
    assert result["weighted_points"] == 2


def test_grade_impossible_and_completed():
    assert not grades([{"weight": 0.9, "grade": 0}, {"weight": 0.1, "grade": None}])["attainable"]
    assert grades([{"weight": 1, "grade": 8}])["final_grade"] == 8
    assert grades([{"weight": 0.2, "grade": 8}])["state"] == "UNKNOWN"


def test_grade_invalid():
    with pytest.raises(CampusError):
        grades([{"weight": 1, "grade": 11}])


def curriculum():
    return [
        {"code": "A", "workload": 60, "completed": False, "prerequisites": []},
        {"code": "B", "workload": 60, "completed": False, "prerequisites": ["A"]},
        {"code": "C", "workload": 60, "completed": False, "prerequisites": ["B"]},
    ]


def test_prerequisites_require_earlier_term():
    plan = plan_curriculum(curriculum())
    assert plan["state"] == "ESTIMATED"
    assert [s["courses"] for s in plan["semesters"]] == [["A"], ["B"], ["C"]]


def test_planner_offerings_workload_and_completed():
    courses = curriculum()
    courses[0]["completed"] = True
    courses[1]["offerings"] = [2]
    result = plan_curriculum(courses, max_load=60, start_term=1)
    assert result["semesters"][0]["courses"] == []
    assert result["semesters"][1]["courses"] == ["B"]
    assert result["semesters"][2]["courses"] == ["C"]


def test_planner_cycles_and_unknown_prereqs():
    courses = curriculum()
    courses[0]["prerequisites"] = ["C"]
    assert plan_curriculum(courses)["state"] == "CONFLICT"
    courses[0]["prerequisites"] = ["X"]
    assert plan_curriculum(courses)["state"] == "BLOCKED"
    del courses[0]["workload"]
    assert plan_curriculum(courses)["state"] == "UNKNOWN"


def test_planner_schedule_overlap():
    a, b = curriculum()[:2]
    b["prerequisites"] = []
    a["schedule"] = [{"day": 1, "start": "10:00", "end": "12:00"}]
    b["schedule"] = [{"day": 1, "start": "11:00", "end": "13:00"}]
    assert plan_curriculum([a, b])["estimated_semesters"] == 2


def test_normalization():
    assert normalize("Engenharia de SofTWare – Aplicações") == "engenharia de software aplicacoes"
