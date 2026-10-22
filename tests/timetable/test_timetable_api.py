"""Post-commit checks for two Timetable backend endpoint functions.

The backend serves HTMX fragments, so these check the HTML and HX headers it
returns. A failed request still answers HTTP 200, flagged with HX-Error.
"""

from uuid import uuid4

import requests

# init_db.py pins alex.wong's demo timetable to this week.
DEMO_WEEK_START = "2026-10-19"


def test_get_timetable_returns_200_and_weekly_grid(api):
    """GET /timetable -> weekly_timetable."""
    response = requests.get(
        api + "/timetable", params={"username": "alex.wong", "week_start": DEMO_WEEK_START}, timeout=10,
    )

    assert response.status_code == 200, response.text
    assert "HX-Error" not in response.headers, response.text
    assert response.headers["Content-Type"].startswith("text/html")
    assert "Advanced Software Development lecture" in response.text, "Expected alex.wong's seeded entry"


def test_post_timetable_returns_201_and_creates_entry(api, database):
    """POST /timetable -> add_entry."""
    # A username of its own keeps the entry clear of seeded clashes and easy to clean up.
    username = "ci-" + uuid4().hex[:12]
    form = {
        "username": username,
        "date": DEMO_WEEK_START,
        "start_time": "10:00",
        "end_time": "11:00",
        "activity_name": "Post-commit endpoint test",
        "category": "Study",
        "notes": "Disposable entry created by the CI/CD test.",
    }
    response = requests.post(api + "/timetable", data=form, timeout=10)
    try:
        assert response.status_code == 201, response.text
        assert "HX-Error" not in response.headers, response.text
        assert response.headers.get("HX-Trigger") == "timetableChanged"
        assert "Post-commit endpoint test was added to your timetable." in response.text

        stored = requests.get(database + "/timetable", params={"username": username}, timeout=5).json()
        assert len(stored) == 1
        for field in ("date", "start_time", "end_time", "activity_name", "category", "notes"):
            assert stored[0][field] == form[field]
        assert stored[0]["day_of_week"] == "Monday"
    finally:
        for entry in requests.get(database + "/timetable", params={"username": username}, timeout=5).json():
            cleanup = requests.post(api + "/timetable/delete", data={"timetable_id": entry["timetable_id"]}, timeout=5)
            assert cleanup.status_code == 200 and "HX-Error" not in cleanup.headers, cleanup.text
