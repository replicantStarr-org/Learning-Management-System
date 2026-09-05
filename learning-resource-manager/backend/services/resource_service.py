import os
from pathlib import Path

from werkzeug.utils import secure_filename

from services.database import NEW_ROW_ID, DatabaseError, fetch, query, transaction

PDF_MAGIC = b"%PDF-"
PDF_MEDIUM = "PDF"

# Runtime writes cannot live in construct_db.sql or populate_db.sql, so the
# statements are kept together here rather than scattered through the routes.
INSERT_RESOURCE = """
    INSERT INTO l_resource (location, author, medium, title, description)
    VALUES (?, ?, ?, ?, ?)
"""
INSERT_RESOURCE_TAG = "INSERT INTO l_resource_tags (l_resource_id, tag_id) VALUES (?, ?)"
SELECT_LOCATION = "SELECT location FROM l_resource WHERE l_resource_id = ?"
DELETE_RESOURCE = "DELETE FROM l_resource WHERE l_resource_id = ?"
DELETE_RESOURCE_TAGS = "DELETE FROM l_resource_tags WHERE l_resource_id = ?"

class ResourceError(RuntimeError):
    pass

def _pdf_directory():
    return Path(os.getenv("CONTENT_PATH", "/content")) / "pdf"

def list_resources():
    return query("l_resource")

def list_resource_cards():
    return query("v_resource_card")

def list_resources_with_tags():
    return query("v_resource_catalogue")

def list_tags():
    return query("tags")

def _store_pdf(upload):
    """Write the upload into the content folder, returning its web location."""
    filename = secure_filename(upload.filename or "")
    if not filename.lower().endswith(".pdf"):
        raise ResourceError("Only PDF files can be uploaded.")

    # Trust the file's own header rather than the name it arrived with.
    header = upload.stream.read(len(PDF_MAGIC))
    upload.stream.seek(0)
    if header != PDF_MAGIC:
        raise ResourceError("That file is not a PDF.")

    directory = _pdf_directory()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ResourceError("The content folder is not writable.") from exc

    # Never overwrite an existing paper; add a counter instead.
    destination = directory / filename
    stem, suffix = destination.stem, destination.suffix
    duplicate = 2
    while destination.exists():
        destination = directory / f"{stem}-{duplicate}{suffix}"
        duplicate += 1

    try:
        upload.save(destination)
    except OSError as exc:
        raise ResourceError("The upload could not be saved.") from exc

    return destination, f"/content/pdf/{destination.name}"

def create_resource(upload, title, author, description, tag_ids):
    title = (title or "").strip()
    if not title:
        raise ResourceError("A title is required.")
    if upload is None or not upload.filename:
        raise ResourceError("Choose a PDF to upload.")

    destination, location = _store_pdf(upload)

    # The resource and its tags go in as one transaction, so the tag rows cannot
    # outlive a resource that failed to save.
    try:
        results = transaction([
            (INSERT_RESOURCE,
             (location, (author or "").strip() or None, PDF_MEDIUM,
              title, (description or "").strip() or None)),
            *((INSERT_RESOURCE_TAG, (NEW_ROW_ID, tag_id)) for tag_id in tag_ids),
        ])
    except DatabaseError as exc:
        # Do not leave a file behind that nothing in the database points at.
        destination.unlink(missing_ok=True)
        raise ResourceError("The resource could not be saved.") from exc

    return results[0]["last_row_id"]

def delete_resource(resource_id):
    rows = fetch(SELECT_LOCATION, (resource_id,))
    if not rows:
        raise ResourceError("That resource no longer exists.")

    transaction([
        (DELETE_RESOURCE_TAGS, (resource_id,)),
        (DELETE_RESOURCE, (resource_id,)),
    ])

    # Only remove files this application owns, under the pdf folder.
    stored = Path(rows[0]["location"])
    target = _pdf_directory() / stored.name
    if stored.parent.as_posix() == "/content/pdf":
        target.unlink(missing_ok=True)
