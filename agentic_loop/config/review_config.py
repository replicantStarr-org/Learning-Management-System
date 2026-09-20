from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModeConfig:
    key: str
    label: str
    prompt_name: str


@dataclass(frozen=True)
class ServiceConfig:
    key: str
    label: str
    directory: str
    workflow: str
    reports_directory: str


MODES = {
    "database": ModeConfig("database", "Database", "database_prompt.txt"),
    "endpoint": ModeConfig("endpoint", "Endpoint Implementation", "endpoint_prompt.txt"),
    "architecture": ModeConfig("architecture", "Application Architecture", "architecture_prompt.txt"),
    "devops": ModeConfig("devops", "DevOps Pipeline", "devops_prompt.txt"),
    "mcp": ModeConfig("mcp", "MCP Server", "mcp_prompt.txt"),
}

SERVICES = {
    "access": ServiceConfig("access", "Shared home page", "access", "access.yml", "access"),
    "subjects": ServiceConfig("subjects", "Subjects Manager", "subjects", "subjects.yml", "subjects"),
    "assignments": ServiceConfig("assignments", "Assignment Manager", "assignments", "assignments.yml", "assignments"),
    "resources": ServiceConfig(
        "resources",
        "Learning Resource Manager",
        "learning-resource-manager",
        "learning-resource-manager.yml",
        "learning-resource-manager",
    ),
    "quizzes": ServiceConfig("quizzes", "Quiz Manager", "quizzes", "quizzes.yml", "quizzes"),
    "timetable": ServiceConfig("timetable", "Timetable Manager", "timetable", "timetable.yml", "timetable"),
}


def service_path(repo_root: Path, service: ServiceConfig) -> Path:
    return repo_root / service.directory
