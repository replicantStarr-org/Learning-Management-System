from agents.model_client import call_model


def review_output(user_request: str, plan: dict, worker_result: dict) -> dict:
    result = call_model("reviewer", {
        "user_request": user_request, "plan": plan, "worker_result": worker_result,
    })
    result["review"] = result.pop("reviewer")
    result["human_approval_required"] = True
    return result
