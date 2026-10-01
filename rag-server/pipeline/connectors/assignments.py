"""Connector for the assignments service."""

from ..connector import Connector, Record, pick

connector = Connector("assignments", "http://localhost:6003")


@connector.entity
def assignments(get):
	"""Index assignment source fields without AI summaries or reminders."""
	for row in get("/assignments"):
		yield Record(
			entity="assignment",
			id=row["assignment_id"],
			title=f"{row['subject_name']}: {row['title']}",
			fields=pick(
				row,
				"subject_name",
				"title",
				"description",
				"requirements",
				"due_at",
				"status",
				"priority",
				"weighting",
			),
		)
