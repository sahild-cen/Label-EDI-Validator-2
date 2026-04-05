from typing import Dict, Any


def generate_validation_diff(result_v1: Dict[str, Any],
                             result_v2: Dict[str, Any]) -> Dict[str, Any]:

    errors_v1 = {e["field"] for e in result_v1.get("errors", [])}
    errors_v2 = {e["field"] for e in result_v2.get("errors", [])}

    new_errors = list(errors_v2 - errors_v1)
    resolved_errors = list(errors_v1 - errors_v2)

    status_change = None
    if result_v1.get("status") != result_v2.get("status"):
        status_change = f"{result_v1.get('status')} → {result_v2.get('status')}"

    return {
        "status_change": status_change,
        "new_errors": new_errors,
        "resolved_errors": resolved_errors,
        "score_change": {
            "old": result_v1.get("compliance_score"),
            "new": result_v2.get("compliance_score")
        }
    }
