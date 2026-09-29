from ..connector import Connector, Record

connector = Connector("timetable", "http://localhost:6005")

# Only timetable entries are indexed. The service's other two tables,
# ai_timetable_plans and ai_advice_logs, hold text the model wrote, which it
# would otherwise cite back as evidence.


@connector.entity
def entries(get):
    # Fan-out: the database only lists entries per user, so /timetable/users
    # (added for this connector) gives every username that has one.
    for username in get("/timetable/users"):
        for entry in get("/timetable", username=username):
            day = entry["day_of_week"]
            # All-day entries are iCal due dates, stored as 00:00-23:59 only to
            # satisfy the schema; that range is not a real time slot.
            if entry["all_day"]:
                title = f"{username} - {entry['activity_name']} (due {day})"
                time = "due date, all day"
            else:
                title = f"{username} - {entry['activity_name']} ({day} {entry['start_time']})"
                time = f"{entry['start_time']} to {entry['end_time']}"

            yield Record(
                entity="timetable_entry",
                id=entry["timetable_id"],
                title=title,
                fields={
                    "student": username,
                    "activity": entry["activity_name"],
                    "category": entry["category"],
                    # The day name as well as the date: people ask what is on
                    # "Monday", and the date alone never contains that word.
                    "day": day,
                    "date": entry["date"],
                    "time": time,
                    "notes": entry["notes"],
                    # A study block the student accepted from the AI plan is their
                    # own entry now, so it is indexed; the flag says where it came
                    # from. Left out (None) rather than "no" on every other entry.
                    "added_from_ai_plan": "yes" if entry["ai_generated"] else None,
                },
            )
