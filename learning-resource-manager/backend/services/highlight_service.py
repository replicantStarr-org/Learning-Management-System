import sqlite3

from services.database import connect

# No sign in yet, so every highlight belongs to the same placeholder user until
# this is wired up to the access service.
DEFAULT_USER_ID = 1

NAME_LIMIT = 64
QUOTE_LIMIT = 2000
COLOURS = {"#ffd54f", "#a5d6a7", "#90caf9", "#f48fb1", "#ce93d8"}

SELECT_FOR_RESOURCE = "SELECT * FROM v_highlight_rect WHERE l_resource_id = ?"
SELECT_SUMMARY_FOR_RESOURCE = "SELECT * FROM v_highlight_summary WHERE l_resource_id = ?"
INSERT_HIGHLIGHT = """
    INSERT INTO highlights (l_resource_id, user_id, name, colour, quote)
    VALUES (?, ?, ?, ?, ?)
"""
INSERT_RECT = """
    INSERT INTO highlight_rects (l_resource_highlight_id, page_number, x, y, width, height)
    VALUES (?, ?, ?, ?, ?, ?)
"""
DELETE_HIGHLIGHT = "DELETE FROM highlights WHERE l_resource_highlight_id = ?"
DELETE_RECTS = "DELETE FROM highlight_rects WHERE l_resource_highlight_id = ?"

class HighlightError(RuntimeError):
    pass

def list_for_resource(resource_id):
    with connect() as conn:
        rows = conn.execute(SELECT_FOR_RESOURCE, (resource_id,)).fetchall()

    return [dict(row) for row in rows]

def list_summary_for_resource(resource_id):
    """One entry per highlight, for the resource popup."""
    with connect() as conn:
        rows = conn.execute(SELECT_SUMMARY_FOR_RESOURCE, (resource_id,)).fetchall()

    return [dict(row) for row in rows]

def _clean_rects(rects):
    """Keep only well formed rectangles, clamped to the page box."""
    cleaned = []
    for rect in rects or []:
        try:
            page_number = int(rect["page_number"])
            values = [float(rect[key]) for key in ("x", "y", "width", "height")]
        except (KeyError, TypeError, ValueError):
            continue

        if page_number < 1 or values[2] <= 0 or values[3] <= 0:
            continue

        x, y, width, height = (min(max(value, 0.0), 1.0) for value in values)
        cleaned.append((page_number, x, y, width, height))

    if not cleaned:
        raise HighlightError("That selection could not be turned into a highlight.")

    return cleaned

def create_highlight(resource_id, name, colour, quote, rects):
    if colour not in COLOURS:
        raise HighlightError("Pick one of the available colours.")

    cleaned = _clean_rects(rects)
    name = (name or "").strip()[:NAME_LIMIT] or None
    quote = (quote or "").strip()[:QUOTE_LIMIT] or None

    try:
        with connect() as conn:
            cursor = conn.execute(
                INSERT_HIGHLIGHT, (resource_id, DEFAULT_USER_ID, name, colour, quote)
            )
            highlight_id = cursor.lastrowid
            for rect in cleaned:
                conn.execute(INSERT_RECT, (highlight_id, *rect))
    except sqlite3.Error as exc:
        raise HighlightError("The highlight could not be saved.") from exc

    return highlight_id

def delete_highlight(highlight_id):
    with connect() as conn:
        conn.execute(DELETE_RECTS, (highlight_id,))
        if conn.execute(DELETE_HIGHLIGHT, (highlight_id,)).rowcount == 0:
            raise HighlightError("That highlight no longer exists.")
