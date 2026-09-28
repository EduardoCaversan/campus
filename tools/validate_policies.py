"""Exercise local real policy evidence; print only coverage/validation metadata."""

import json
from pathlib import Path

from campus.config import load_config
from campus.policies import analyze_policies, policy_grade
from campus.service import Campus
from campus.store import single

campus = Campus(load_config(home=Path.cwd() / ".campus"))
try:
    print(json.dumps({"analysis": analyze_policies(campus.store)}))
    print(json.dumps({"repeat_analysis": analyze_policies(campus.store)}))
    for course in campus.store.entities("course"):
        policy = single(course, "grading_policy")
        if not policy:
            continue
        row = policy_grade(campus.store, course["id"])[0]
        hypothetical = policy_grade(
            campus.store, course["id"], {key: 7 for key in policy["coefficients"]}
        )[0]
        print(
            json.dumps(
                {
                    "policy_state": policy["state"],
                    "component_count": len(policy["coefficients"]),
                    "passing_threshold_present": policy["passing_grade"] is not None,
                    "scale_present": policy["scale"] is not None,
                    "recorded_components_matched": len(policy["coefficients"])
                    - len(row.get("missing_components", [])),
                    "unresolved_rules": policy["unresolved"],
                    "source_evidence_linked": bool(policy.get("source_evidence")),
                    "automatic_scenario_calculated": hypothetical.get("final_grade") is not None,
                    "normal_answer_state": row["state"],
                },
                ensure_ascii=True,
            )
        )
        code = single(course, "code")
        if code:
            answer = campus.ask(f"qual minha média atual em {code}?")
            print(
                json.dumps(
                    {
                        "automatic_question_state": answer.get("state"),
                        "policy_engine_routed": bool(
                            answer.get("data") and "components" in answer["data"][0]
                        ),
                    }
                )
            )
    print(
        json.dumps(
            {
                "requirements": len(campus.store.entities("requirement")),
                "equivalencies": len(campus.store.entities("equivalence")),
                "announcements": len(campus.store.entities("announcement")),
                "resources": len(campus.store.entities("resource")),
            }
        )
    )
finally:
    campus.store.close()
