from ..connector import Connector, Record, pick

# The backend, not the database: the database port is deliberately unpublished
# and only accepts raw SQL.
connector = Connector("learning-resources", "http://localhost:7050")


@connector.entity
def resources(get):
    # /api/resources/catalogue rather than /all: it carries each resource's tags,
    # which are the only place its subject is recorded. No title or description
    # of the maths papers says "mathematics"; their tag does.
    for resource in get("/api/resources/catalogue"):
        yield Record(
            entity="learning_resource",
            id=resource["l_resource_id"],
            title=resource["title"],
            fields={
                **pick(resource, "title", "author", "medium"),
                # "topics" rather than "tags": keys are indexed too, and people ask
                # what a paper is about, not how it is tagged.
                "topics": resource["tags"],
                "description": resource["description"],
            },
        )
