from agents.model_client import call_model


def generate_output(user_request: str, plan: dict, evidence: dict) -> dict:
    result = call_model("worker", {"user_request": user_request, "plan": plan, "evidence": evidence})
    result["output"] = result.pop("worker")
    result.update(evidence)
    result["human_approval_required"] = True
    return result
