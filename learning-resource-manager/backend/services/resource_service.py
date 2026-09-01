import os
import sqlite3

# Query shapes live in database/construct_db.sql as views, so the only SQL here
# is the name of the view to read.
def query(view):
    db_full_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    with sqlite3.connect(db_full_path + "/" + db_name) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {view}")

        return cursor.fetchall()

def list_resources():
    return query("l_resource")

def list_resource_cards():
    return query("v_resource_card")

def list_resources_with_tags():
    return query("v_resource_catalogue")
