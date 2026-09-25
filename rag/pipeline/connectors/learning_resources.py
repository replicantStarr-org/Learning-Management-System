from ..connector import Connector, Record, pick

# The backend, not the database: the database port is deliberately unpublished
# and only accepts raw SQL.
connector = Connector("learning-resources", "http://localhost:7050")

# /api/resources/all returns each row as an array in the column order of the
# l_resource table (learning-resource-manager/database/construct_db.sql).
COLUMNS = ("l_resource_id", "location", "author", "medium", "title", "description")


@connector.entity
def resources(get):
    for row in get("/api/resources/all"):
        if len(row) != len(COLUMNS):
            raise ValueError(f"expected {len(COLUMNS)} columns per resource, got {len(row)}; has l_resource changed?")
        resource = dict(zip(COLUMNS, row))
        yield Record(
            entity="learning_resource",
            id=resource["l_resource_id"],
            title=resource["title"],
            fields=pick(resource, "title", "author", "medium", "description"),
        )
