from ..common import Connector, Record, pick

connector = Connector("timetable", "http://localhost:6005")

# The API returns one user's entries per request and nothing lists the users,
# so they are named here. A user missing from this list is never indexed.
USERNAMES = ["alex.wong", "priya.patel", "sam.turner"]

# Only entries are indexed. The plans and advice tables hold earlier model
# output, which would have the model citing itself as evidence.


@connector.entity
def entries(get):
    for username in USERNAMES:
        for entry in get("/timetable", username=username):
            yield Record(
                entity="timetable_entry",
                id=entry["timetable_id"],
                title=f"{entry['username']}: {entry['activity_name']}, {entry['day_of_week']} {entry['date']}",
                fields=pick(
                    entry,
                    "username", "activity_name", "category", "day_of_week", "date",
                    "start_time", "end_time", "notes",
                ),
            )
