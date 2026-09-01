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

@resources_bp.route('all_html')
def get_all_html():
    rows = get_all()
    html = ""
    for row in rows:
        html += "<tr>"
        for r in row:
            html += f"<td>{r}</td>"
        html += "</tr>"
   
    return html
