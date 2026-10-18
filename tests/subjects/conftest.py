import os
import time

import pytest
import requests


@pytest.fixture(scope="session")
def api():
    """Wait for the backend and its database before testing the two endpoints."""
    url = os.getenv("SUBJECT_BACKEND_URL", "http://localhost:5001").rstrip("/") + "/api/v1"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if requests.get(url + "/subjects", timeout=3).status_code == 200:
                return url
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail("Subjects API/database did not become ready within 60 seconds")
