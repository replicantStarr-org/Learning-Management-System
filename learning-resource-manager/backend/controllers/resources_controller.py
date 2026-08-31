from flask import Blueprint
import os
import sqlite3

resources_bp = Blueprint('resources', __name__)

@resources_bp.route('/resources')
def get_resources():
    db_name = os.getenv("DATABASE_NAME")
    with sqlite.connect(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM l_resource")

        return cursor.fetchall()
