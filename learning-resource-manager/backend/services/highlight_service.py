import re
import sqlite3

from services.database import connect

# No sign in yet, so every highlight belongs to the same placeholder user until
# this is wired up to the access service.
DEFAULT_USER_ID = 1

NAME_LIMIT = 64
QUOTE_LIMIT = 2000
COMMENT_LIMIT = 1000

# Offered as swatches in the reader. Any other '#rrggbb' is equally valid; these
# are a starting point, not the set of allowed colours.
SUGGESTED_COLOURS = ("#ffd54f", "#a5d6a7", "#90caf9", "#f48fb1", "#ce93d8")
COLOUR_PATTERN = re.compile(r"\A#[0-9a-fA-F]{6}\Z")

SELECT_FOR_RESOURCE = "SELECT * FROM v_highlight_rect WHERE l_resource_id = ?"
SELECT_SUMMARY_FOR_RESOURCE = "SELECT * FROM v_highlight_summary WHERE l_resource_id = ?"
SELECT_CATALOGUE = "SELECT * FROM v_highlight_catalogue"
INSERT_HIGHLIGHT = """
    INSERT INTO highlights (l_resource_id, user_id, name, colour, quote, comment)
    VALUES (?, ?, ?, ?, ?, ?)
"""
UPDATE_HIGHLIGHT = """
    UPDATE highlights
       SET name = ?, colour = ?, comment = ?
     WHERE l_resource_highlight_id = ?
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

def list_highlight_catalogue():
    """Every highlight in the library, for the chat service to read back."""
    with connect() as conn:
        return conn.execute(SELECT_CATALOGUE).fetchall()

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

def _clean_colour(colour):
    """Any '#rrggbb' the colour picker can produce, stored in one casing."""
    colour = (colour or "").strip()
    if not COLOUR_PATTERN.match(colour):
        raise HighlightError("Pick a colour in '#rrggbb' form.")

    return colour.lower()

def create_highlight(resource_id, name, colour, quote, comment, rects):
    colour = _clean_colour(colour)
    cleaned = _clean_rects(rects)
    name = (name or "").strip()[:NAME_LIMIT] or None
    quote = (quote or "").strip()[:QUOTE_LIMIT] or None
    comment = (comment or "").strip()[:COMMENT_LIMIT] or None

    try:
        with connect() as conn:
            cursor = conn.execute(
                INSERT_HIGHLIGHT,
                (resource_id, DEFAULT_USER_ID, name, colour, quote, comment),
            )
            highlight_id = cursor.lastrowid
            for rect in cleaned:
                conn.execute(INSERT_RECT, (highlight_id, *rect))
    except sqlite3.Error as exc:
        raise HighlightError("The highlight could not be saved.") from exc

    return highlight_id

def update_highlight(highlight_id, name, colour, comment):
    """Replace the three fields a reader can edit after the fact.

    The quote and the rectangles come from the selection, so they are fixed once
    the highlight exists; only what it is called, how it looks and what was
    written about it can change.
    """
    colour = _clean_colour(colour)
    name = (name or "").strip()[:NAME_LIMIT] or None
    comment = (comment or "").strip()[:COMMENT_LIMIT] or None

    try:
        with connect() as conn:
            changed = conn.execute(
                UPDATE_HIGHLIGHT, (name, colour, comment, highlight_id)
            ).rowcount
    except sqlite3.Error as exc:
        raise HighlightError("The highlight could not be saved.") from exc

    if changed == 0:
        raise HighlightError("That highlight no longer exists.")

    return highlight_id

def delete_highlight(highlight_id):
    with connect() as conn:
        conn.execute(DELETE_RECTS, (highlight_id,))
        if conn.execute(DELETE_HIGHLIGHT, (highlight_id,)).rowcount == 0:
            raise HighlightError("That highlight no longer exists.")
