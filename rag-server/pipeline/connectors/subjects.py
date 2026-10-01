"""Connector for the subjects service."""

from ..connector import Connector, Record


connector = Connector("subjects", "http://localhost:6001")


@connector.entity
def subjects(get):
    """Index the complete subject returned by the detail endpoint.

    The list endpoint intentionally contains only the fields needed to render
    subject cards, so fetch each detail record before creating its RAG record.
    """
    for row in get("/subjects"):
        subject = get(f"/subjects/{row['subject_id']}")
        tags = [tag["name"] for tag in subject["tags"]]
        yield Record(
            entity="subject",
            id=subject["subject_id"],
            title=f"{subject['code']} - {subject['name']}",
            fields={
                "code": subject["code"],
                "name": subject["name"],
                "description": subject["description"],
                "semester": subject["semester"],
                "coordinator": subject["coordinator"],
                "status": subject["status"],
                "tags": tags,
            },
        )
