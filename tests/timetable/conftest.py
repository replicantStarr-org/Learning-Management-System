import os
import time

import pytest
import requests


@pytest.fixture(scope="session")
def database():
    """The Timetable database service, used only to find and clean up test data."""
    return os.getenv("TIMETABLE_DATABASE_URL", "http://localhost:6005").rstrip("/")


@pytest.fixture(scope="session")
def api(database):
    """Wait for the backend and its database before testing the two endpoints."""
    url = os.getenv("TIMETABLE_BACKEND_URL", "http://localhost:5005").rstrip("/")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if (requests.get(url + "/", timeout=3).status_code == 200
                    and requests.get(database + "/timetable/users", timeout=3).status_code == 200):
                return url
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail("Timetable backend/database did not become ready within 60 seconds")
