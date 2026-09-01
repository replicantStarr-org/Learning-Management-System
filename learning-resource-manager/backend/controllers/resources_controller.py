from flask import Blueprint
from markupsafe import escape
import os
import sqlite3

resources_bp = Blueprint('resources', __name__)

def query(sql):
    db_full_path = os.getenv("DATABASE_PATH")
    db_name = os.getenv("DATABASE_NAME")
    with sqlite3.connect(db_full_path + "/" + db_name) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)

        return cursor.fetchall()

@resources_bp.route('/all')
def get_all():
    return [tuple(row) for row in query("SELECT * FROM l_resource")]

@resources_bp.route('/all_html')
def get_all_html():
    rows = query("SELECT title, author, description, location FROM l_resource ORDER BY title")
    if not rows:
        return '<p class="text-secondary">No learning resources yet.</p>'

    return "".join(render_card(row) for row in rows)

def render_card(row):
    title = escape(row["title"])
    author = escape(row["author"] or "Unknown author")
    description = escape(row["description"] or "No description available.")
    location = escape(row["location"])

    return f"""
        <div class="col">
            <article class="card feature-card resource-card h-100" role="button" tabindex="0"
                     data-title="{title}" data-author="{author}"
                     data-description="{description}" data-location="{location}">
                <div class="resource-thumb">
                    <canvas class="resource-thumb-canvas" data-location="{location}"></canvas>
                    <div class="resource-thumb-fallback small">Preview unavailable</div>
                </div>
                <div class="card-body d-flex flex-column">
                    <h2 class="card-title h6 mb-1">{title}</h2>
                    <p class="resource-author small mb-3">{author}</p>
                    <p class="resource-description small mb-0">{description}</p>
                </div>
            </article>
        </div>
    """
