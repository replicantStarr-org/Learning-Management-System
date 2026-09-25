from ..common import Connector, Record, pick

connector = Connector("subjects", "http://localhost:6001")


@connector.entity
def subjects(get):
    # The list only has code and name; the description lives on the detail.
    for row in get("/subjects"):
        subject = get(f"/subjects/{row['subject_id']}")
        yield Record(
            entity="subject",
            id=subject["subject_id"],
            title=f"{subject['code']} {subject['name']}",
            fields={
                **pick(subject, "code", "name", "semester", "coordinator", "status"),
                "tags": [tag["name"] for tag in subject["tags"]],
                "description": subject["description"],
            },
        )
