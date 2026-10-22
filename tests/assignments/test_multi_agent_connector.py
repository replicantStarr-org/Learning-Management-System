"""Unit checks for the Assignments evidence adapter used by the shared server."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

SERVER_ROOT = Path(__file__).resolve().parents[2] / "multi-agent-server"
sys.path.insert(0, str(SERVER_ROOT))

from connectors.assignments import collect_evidence


def test_collect_evidence_returns_bounded_assignment_fields():
    row = {
        "assignment_id": 42,
        "subject_id": 1,
        "subject_name": "ASD101",
        "title": "Release task",
        "description": "A" * 2100,
        "requirements": "Submit a report",
        "due_at": "2099-01-01 09:00:00",
        "status": "In Progress",
        "priority": "High",
        "weighting": 20,
        "ignored_internal_field": "not shared with agents",
    }
    response = Mock()
    response.json.return_value = [row]

    with patch("connectors.assignments.requests.get", return_value=response) as get:
        result = collect_evidence()

    get.assert_called_once_with("http://localhost:6003/assignments", timeout=10.0)
    response.raise_for_status.assert_called_once_with()
    assert result["evidence_count"] == 1
    assert result["evidence"][0]["source"] == "assignments:/assignments/42"
    assert len(result["evidence"][0]["fields"]["description"]) == 2000
    assert "ignored_internal_field" not in result["evidence"][0]["fields"]
    assert result["limitations"] == ["Assignment 42 field description was truncated."]