import os
import sqlite3

def connect():
    db_full_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    conn = sqlite3.connect(db_full_path + "/" + db_name)
    conn.row_factory = sqlite3.Row

    return conn

# Query shapes live in database/construct_db.sql as views, so the only SQL here
# is the name of the view to read.
def query(view):
    with connect() as conn:
        return conn.execute(f"SELECT * FROM {view}").fetchall()
