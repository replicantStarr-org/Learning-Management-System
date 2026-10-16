from agents.model_client import call_model


def default_steps() -> list[dict]:
    return [
        {"step": 1, "agent": "planner_agent", "action": "Create workflow plan"},
        {"step": 2, "agent": "worker_agent", "action": "Generate output from supplied database evidence"},
        {"step": 3, "agent": "reviewer_agent", "action": "Review risk, correction, retest and recommendation"},
        {"step": 4, "agent": "human_reviewer", "action": "Accept, partially accept, or reject"},
    ]


def plan_workflow(user_request: str, evidence: dict) -> dict:
    result = call_model("planner", {"user_request": user_request, "evidence": evidence})
    result["plan"] = result.pop("planner")
    result.update(objective=user_request, steps=default_steps(), human_approval_required=True)
    return result
