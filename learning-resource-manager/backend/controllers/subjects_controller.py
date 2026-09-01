from flask import Blueprint
import os
import sqlite3

subjects_bp = Blueprint('subjects', __name__)

@subjects_bp.route('/all')
def get_all():
    db_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    with sqlite3.connect(db_path + "/" + db_name) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM l_resource_subject")

        return cursor.fetchall()
