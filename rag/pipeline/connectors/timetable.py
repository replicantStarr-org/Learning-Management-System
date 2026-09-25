"""Connector for the timetable service. Not implemented yet.

Read AGENTS.md in this folder before writing it; learning_resources.py is a
working example. Until an entity function is registered, ingestion skips this
service.
"""

from ..common import Connector

connector = Connector("timetable", "http://localhost:6005")
