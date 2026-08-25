import os
import sqlite3

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "subjects.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(
    DATABASE_NAME
)

cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS subjects;")
cursor.execute("DROP TABLE IF EXISTS subject_ai_summaries;")

cursor.execute("""
CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    semester TEXT NOT NULL,
    coordinator TEXT NOT NULL,
    status TEXT NOT NULL,
    last_update DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")


cursor.execute("""
CREATE TRIGGER update_subject_timestamp 
AFTER UPDATE ON subjects
FOR EACH ROW
BEGIN
    UPDATE subjects 
    SET last_update = CURRENT_TIMESTAMP 
    WHERE subject_id = OLD.subject_id;
END;
""")

cursor.execute("""
CREATE TABLE subject_ai_summaries (
    summary_id INTEGER PRIMARY KEY,
    ai_response TEXT NOT NULL,
    subject_id INTEGER REFERENCES subjects(subject_id),
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

conn.commit()
conn.close()


# TODO: data seeding
