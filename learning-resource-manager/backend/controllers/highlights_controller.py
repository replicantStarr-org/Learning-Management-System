from flask import Blueprint
import os
import sqlite3

highlights_bp = Blueprint('highlights', __name__)

@highlights_bp.route('/all')
def get_all():
    db_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    with sqlite3.connect(db_path + "/" + db_name) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM highlights")

        return cursor.fetchall()

@highlights_bp.route("/all_html")
def get_all_html():
    rows = get_all()
    print(rows)
    html = ""
    for row in rows:
        html += f"<tr><td>{row[1]}</td></tr>"
   
    return html
