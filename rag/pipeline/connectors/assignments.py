from ..common import Connector, Record, pick

connector = Connector("assignments", "http://localhost:6003")


@connector.entity
def assignments(get):
    for assignment in get("/assignments"):
        yield Record(
            entity="assignment",
            id=assignment["assignment_id"],
            title=assignment["title"],
            fields=pick(
                assignment,
                "subject_name", "title", "due_at", "status", "priority", "weighting",
                "description", "requirements",
            ),
        )
