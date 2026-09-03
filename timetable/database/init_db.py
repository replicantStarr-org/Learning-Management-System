import os
import sqlite3
from datetime import datetime, timedelta

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "timetable.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS timetable_entries;")
cursor.execute("DROP TABLE IF EXISTS ai_timetable_plans;")
cursor.execute("DROP TABLE IF EXISTS ai_advice_logs;")

cursor.execute("""
CREATE TABLE timetable_entries (
    timetable_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    date DATE NOT NULL,
    day_of_week TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    category TEXT NOT NULL,
    notes TEXT,
    ai_generated BOOLEAN NOT NULL DEFAULT 0,
    all_day BOOLEAN NOT NULL DEFAULT 0,
    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TRIGGER update_timetable_entry_timestamp
AFTER UPDATE ON timetable_entries
FOR EACH ROW
BEGIN
    UPDATE timetable_entries
    SET last_updated = CURRENT_TIMESTAMP
    WHERE timetable_id = OLD.timetable_id;
END;
""")

cursor.execute("""
CREATE TABLE ai_timetable_plans (
    plan_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    plan_text TEXT NOT NULL,
    suggested_entries TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    regenerated_at DATETIME
);
""")

cursor.execute("""
CREATE TABLE ai_advice_logs (
    advice_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    question TEXT,
    advice_text TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

today = datetime.now().date()
monday = today - timedelta(days=today.weekday())


def on(day_offset):
    return (monday + timedelta(days=day_offset)).isoformat()


def weekday_name(day_offset):
    return (monday + timedelta(days=day_offset)).strftime("%A")


entries = [
    ("alex.wong", 0, "09:00", "10:30", "Advanced Software Development lecture", "Class", "Room 4.20", 0),
    ("alex.wong", 0, "13:00", "15:00", "ASD study group", "Study", "Prep for sprint review", 0),
    ("alex.wong", 1, "11:00", "12:30", "Database Systems tutorial", "Class", "", 0),
    ("alex.wong", 1, "18:00", "19:30", "Soccer training", "Personal", "", 0),
    ("alex.wong", 2, "09:00", "11:00", "Web Application Engineering workshop", "Class", "", 0),
    ("alex.wong", 2, "15:00", "17:00", "Part-time job - cafe shift", "Work", "", 0),
    ("alex.wong", 3, "10:00", "12:00", "Algorithms revision", "Study", "Past papers", 0),
    ("alex.wong", 4, "09:00", "10:30", "Advanced Software Development lecture", "Class", "Room 4.20", 0),
    ("alex.wong", 4, "19:00", "20:00", "Guitar lesson", "Personal", "", 0),
    ("alex.wong", 6, "10:00", "11:30", "Weekly meal prep", "Personal", "", 0),
    ("priya.patel", 0, "09:00", "10:30", "Advanced Software Development lecture", "Class", "Room 4.20", 0),
    ("priya.patel", 1, "13:00", "14:00", "Gym session", "Personal", "", 0),
    ("priya.patel", 2, "10:00", "12:00", "Cybersecurity Fundamentals lab", "Class", "", 0),
    ("priya.patel", 3, "16:00", "18:00", "Study - Cloud Computing assignment", "Study", "", 1),
    ("priya.patel", 5, "10:00", "11:00", "Volunteering at library", "Personal", "", 0),
    ("sam.turner", 0, "09:00", "10:30", "Advanced Software Development lecture", "Class", "Room 4.20", 0),
]

seed_entries = [
    (
        username,
        on(day_offset),
        weekday_name(day_offset),
        start,
        end,
        activity,
        category,
        notes,
        ai_generated,
    )
    for username, day_offset, start, end, activity, category, notes, ai_generated in entries
]

cursor.executemany(
    """
    INSERT INTO timetable_entries (
        username, date, day_of_week, start_time, end_time, activity_name, category, notes, ai_generated
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    seed_entries,
)

plans = [
    ("alex.wong", "This week your schedule is well balanced, but Tuesday evening (soccer straight after your cafe shift) leaves little recovery time before Wednesday's study block. Consider moving the algorithms revision earlier in the week and adding a short review session right after each lecture while the material is still fresh."),
    ("alex.wong", "Your ASD study group and Web Application Engineering workshop sit on different days - use the study group session to consolidate the workshop content instead of starting from scratch each time."),
    ("priya.patel", "You have a good spread of classes but no dedicated study block before the Cloud Computing assignment is due. Add at least one 90-minute focused session earlier in the week rather than relying on Thursday's block alone."),
    ("priya.patel", "Volunteering and the gym session both fall on days without classes, which protects your class days for focused work - keep this pattern going."),
    ("sam.turner", "Only one entry is recorded this week. Add your remaining classes and any regular commitments so future plans can give more specific advice."),
    ("alex.wong", "Reviewed schedule: workload is concentrated early in the week. Spreading Thursday's study session across two shorter sessions may improve retention."),
    ("priya.patel", "The Cybersecurity lab and gym session are adjacent - schedule a short break between technical lab work and physical activity."),
    ("sam.turner", "Add personal time blocks to avoid an all-study, all-class week."),
    ("alex.wong", "The Friday evening guitar lesson is a good wind-down after a full week of classes and work - keep protecting personal time like this."),
    ("priya.patel", "Consider moving the Cloud Computing study block earlier in the week if the assignment deadline falls early the following week."),
]

cursor.executemany(
    "INSERT INTO ai_timetable_plans (username, plan_text) VALUES (?, ?)",
    plans,
)

advice_logs = [
    ("alex.wong", "How should I balance my part-time job with study this week?", "Your cafe shift on Wednesday finishes at 17:00, leaving a solid evening window - use it for lighter review rather than starting new material, and protect Thursday morning for deeper study before energy dips later in the day."),
    ("alex.wong", None, "Your week looks front-loaded with classes. Try blocking 30 minutes after each lecture to summarise notes while the content is fresh, which reduces the need for longer revision sessions later."),
    ("priya.patel", "I have an assignment due soon, what should I prioritise?", "Move your Cloud Computing study block earlier if possible, and break the assignment into two shorter working sessions rather than one long one - this tends to reduce last-minute pressure."),
    ("priya.patel", None, "Your schedule balances classes with personal activities well. Keep at least one evening fully free each week to avoid burnout."),
    ("sam.turner", "I only have one class logged, any general advice?", "Add your other regular commitments so advice can be tailored - in the meantime, aim to block out fixed study windows on the days without classes."),
    ("alex.wong", "Is Tuesday too packed?", "Tuesday currently has a tutorial followed by soccer training with no break - consider a 15-30 minute buffer between the two so you're not rushing straight from class to training."),
    ("priya.patel", "How can I fit in more revision time?", "Your Monday and Wednesday classes leave the afternoons free - use one of those afternoons consistently each week as a fixed revision slot rather than fitting it in around other commitments."),
    ("sam.turner", None, "Once more entries are added, advice can focus on specific gaps or clashes in your week."),
    ("alex.wong", "Should I move my guitar lesson?", "Friday evening works well as a wind-down after a full week - there's no need to move it unless it conflicts with a new commitment."),
    ("priya.patel", "Any tips for balancing volunteering with study?", "Saturday's volunteering session doesn't overlap with any study blocks, so it's already well placed - just make sure Sunday keeps some unstructured rest time before the new week starts."),
]

cursor.executemany(
    "INSERT INTO ai_advice_logs (username, question, advice_text) VALUES (?, ?, ?)",
    advice_logs,
)

conn.commit()
conn.close()
