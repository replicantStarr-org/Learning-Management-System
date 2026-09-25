"""Connector for the subjects service. Not implemented yet.

Read AGENTS.md in this folder before writing it; learning_resources.py is a
working example. Until an entity function is registered, ingestion skips this
service.
"""

from ..common import Connector

connector = Connector("subjects", "http://localhost:6001")
