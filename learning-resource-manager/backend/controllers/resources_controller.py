from flask import Blueprint
import os
import sqlite3

resources_bp = Blueprint('resources', __name__)

@resources_bp.route('/all')
def get_all():
    db_full_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    print(db_full_path)
    with sqlite3.connect(db_full_path + "/" + db_name) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM l_resource")

        return cursor.fetchall()
