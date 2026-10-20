"""Checks for two Learning Resource Manager backend endpoints.

Runs against a live backend (the compose stack). Set LRM_BACKEND_URL to point
somewhere other than the local default.
"""

import os

import requests

API = os.getenv("LRM_BACKEND_URL", "http://localhost:5002").rstrip("/") + "/api/resources"


def test_get_catalogue_returns_resources_with_tags():
    """GET /api/resources/catalogue -> get_catalogue."""
    response = requests.get(API + "/catalogue", timeout=10)

    assert response.status_code == 200, response.text
    resources = response.json()
    assert isinstance(resources, list)
    assert resources, "Expected the seeded learning resources"
    assert all({"l_resource_id", "title", "tags"} <= resource.keys() for resource in resources)

    attention = next(r for r in resources if r["title"] == "Attention Is All You Need")
    assert "Deep Learning" in attention["tags"]


def test_get_tags_returns_seeded_tags():
    """GET /api/resources/tags -> get_tags."""
    response = requests.get(API + "/tags", timeout=10)

    assert response.status_code == 200, response.text
    tags = response.json()
    assert isinstance(tags, list)
    assert {"Computer Science", "Machine Learning", "Deep Learning"} <= {tag["name"] for tag in tags}
