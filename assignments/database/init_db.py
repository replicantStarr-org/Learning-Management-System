import os
import sqlite3
from datetime import datetime, timedelta

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "assignments.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS assignment_reminders;")
cursor.execute("DROP TABLE IF EXISTS assignment_recommendations;")
cursor.execute("DROP TABLE IF EXISTS assignment_summaries;")
cursor.execute("DROP TABLE IF EXISTS assignments;")

cursor.execute("""
CREATE TABLE assignments (
    assignment_id INTEGER PRIMARY KEY,
    subject_id INTEGER,
    subject_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    requirements TEXT NOT NULL,
    due_at DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'Not Started',
    priority TEXT NOT NULL DEFAULT 'Medium',
    weighting INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_update DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TRIGGER update_assignment_timestamp
AFTER UPDATE ON assignments
FOR EACH ROW
BEGIN
    UPDATE assignments
    SET last_update = CURRENT_TIMESTAMP
    WHERE assignment_id = OLD.assignment_id;
END;
""")

# Cached AI output. Kept as history (one row per generation) rather than a column on
# assignments so the model used and the generation time stay auditable, mirroring
# subject_ai_summaries in the Subject Management feature.
cursor.execute("""
CREATE TABLE assignment_summaries (
    summary_id INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(assignment_id),
    ai_response TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE assignment_recommendations (
    recommendation_id INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(assignment_id),
    title TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    -- Set when the recommendation was matched to a real row in the Learning Resource
    -- Manager feature; NULL when the model suggested material we do not hold.
    source_resource_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE assignment_reminders (
    reminder_id INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(assignment_id),
    remind_at DATETIME NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("CREATE INDEX idx_assignments_due_at ON assignments(due_at);")
cursor.execute("CREATE INDEX idx_reminders_remind_at ON assignment_reminders(remind_at);")


NOW = datetime.now().replace(minute=0, second=0, microsecond=0)


def due(days, hour=23):
    """Seed due dates relative to build time so 'upcoming' always has data to show."""
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=59).strftime("%Y-%m-%d %H:%M:%S")


# subject_id/subject_name mirror the seed data in subjects/database/init_db.py. The subjects
# feature owns that schema; this feature only stores a denormalised snapshot, per the
# cross-feature integration rule in the top-level design.md.
ASSIGNMENTS = [
    (1, "ASD101 - Advanced Software Development", "Release 0 Technical Report",
     "Document the Release 0 microservices architecture, the agentic workflow and the DevOps pipeline for the team project.",
     "Cover the repository structure, one architecture diagram per microservice, an integrated Release 0 diagram, a Docker Compose diagram, the Plan/Act/Observe/Adapt workflow, CI evidence and known limitations. One PDF per group, maximum 25 pages.",
     due(2), "In Progress", "High", 20),
    (1, "ASD101 - Advanced Software Development", "Microservice Feature Implementation",
     "Build the frontend, backend and database containers for your assigned feature and integrate them with the team application.",
     "Implement full CRUD through the frontend, seed every table with at least ten records, expose a REST API from the backend, integrate one AI capability through Ollama and containerise all three services.",
     due(5), "In Progress", "High", 25),
    (1, "ASD101 - Advanced Software Development", "CI/CD Workflow Evidence",
     "Produce a GitHub Actions workflow that builds and validates your microservices, and collect the run evidence.",
     "The workflow must build the Docker images, smoke check every service over HTTP, tear the stack down on failure and upload a JSON and Markdown evidence report as an artefact.",
     due(9), "Not Started", "Medium", 10),
    (2, "SEP202 - Software Engineering Practices", "Requirements Elicitation Interview",
     "Run a stakeholder interview and turn the transcript into a prioritised requirements backlog.",
     "Submit the interview transcript, at least fifteen functional requirements, five non-functional requirements and a MoSCoW prioritisation table with a short justification for each Must item.",
     due(12), "Not Started", "Medium", 15),
    (2, "SEP202 - Software Engineering Practices", "Sprint Retrospective Report",
     "Reflect on the first sprint using the team's velocity data and burndown chart.",
     "Include the sprint goal, committed versus completed story points, the burndown chart, three improvement actions with owners, and evidence from the team board.",
     due(-3), "Submitted", "Low", 10),
    (3, "DBS303 - Database Systems", "Normalisation Workshop",
     "Normalise the supplied university enrolment schema to third normal form.",
     "Show the unnormalised relation, the functional dependencies, and each of 1NF, 2NF and 3NF with the reasoning for every decomposition. Provide the final DDL as runnable SQL.",
     due(4), "Not Started", "High", 20),
    (3, "DBS303 - Database Systems", "Query Optimisation Case Study",
     "Profile five slow queries against the sample dataset and make them fast.",
     "For each query provide the original plan, the indexes or rewrites applied, the new plan, and a measured before/after timing over at least three runs.",
     due(16), "Not Started", "Medium", 20),
    (4, "WEB404 - Web Application Development", "Accessible Component Library",
     "Build a small component library that meets WCAG 2.1 AA.",
     "Deliver at least six components with keyboard support, visible focus states, ARIA labelling where native semantics are unavailable, and an audit report from an automated checker plus manual keyboard testing notes.",
     due(7), "In Progress", "Medium", 25),
    (4, "WEB404 - Web Application Development", "Progressive Enhancement Essay",
     "Argue for or against hypermedia-driven interfaces compared with client-side frameworks.",
     "1500 words, at least eight peer-reviewed references in APA 7, and a worked example contrasting the two approaches for the same feature.",
     due(21), "Not Started", "Low", 15),
    (5, "AIT505 - Applied Artificial Intelligence", "Prompt Injection Threat Model",
     "Threat model an LLM-backed feature and propose mitigations.",
     "Identify at least six attack paths across direct and indirect injection, rate each by likelihood and impact, and specify a concrete mitigation with the layer it belongs to (input, prompt, model, output).",
     due(1), "In Progress", "High", 20),
    (5, "AIT505 - Applied Artificial Intelligence", "Retrieval Augmented Generation Prototype",
     "Ground a local model's answers in a document collection and evaluate the result.",
     "Submit the ingestion pipeline, the retrieval strategy, ten evaluation questions with grounded and ungrounded answers side by side, and a short analysis of the failure cases.",
     due(28), "Not Started", "Medium", 30),
    (5, "AIT505 - Applied Artificial Intelligence", "Model Evaluation Poster",
     "Compare two open-source models on the same task and present the results as a poster.",
     "One A1 poster covering the task, the evaluation metric, the sample size, the results table and a limitations section. Include the hardware used and the wall-clock cost per response.",
     due(-9), "Graded", "Low", 10),
]

cursor.executemany(
    """
    INSERT INTO assignments
        (subject_id, subject_name, title, description, requirements, due_at, status, priority, weighting)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    ASSIGNMENTS,
)

SUMMARIES = [
    (1, "Focus on evidence: the report is graded on what you can show, not what you claim. Build the diagrams first, then write around them, and keep one section per marking bullet so nothing is missed.", "qwen2.5:0.5b"),
    (2, "Start from the database service and work outwards - the backend and frontend are both blocked on its schema. Seed the tables early so the CRUD screens have something to render.", "qwen2.5:0.5b"),
    (3, "The smoke check is the risky part. Get one service probing green locally before wiring the other two, and always tear the stack down with an always() clause.", "qwen2.5:0.5b"),
    (4, "Prioritisation is where the marks are. Interview first, transcribe verbatim, then justify every Must requirement against a stakeholder quote.", "qwen2.5:0.5b"),
    (5, "Retrospectives are marked on the actions, not the narrative. Name an owner and a due date for each improvement action.", "qwen2.5:0.5b"),
    (6, "Write the functional dependencies down before decomposing anything; almost every lost mark in this task traces back to a missed dependency.", "qwen2.5:0.5b"),
    (7, "Measure before you optimise. Capture the baseline plan and timing for all five queries first, otherwise the improvement cannot be evidenced.", "qwen2.5:0.5b"),
    (8, "Keyboard support and focus visibility carry the most weight. Test every component with the mouse unplugged before running the automated audit.", "qwen2.5:0.5b"),
    (9, "The essay wants a defended position, not a survey. Pick a side in the introduction and use the worked example as your strongest evidence.", "qwen2.5:0.5b"),
    (10, "Cover indirect injection through retrieved documents, not just the user prompt - that is the path most submissions miss.", "qwen2.5:0.5b"),
    (11, "Build the evaluation set before the pipeline. Ten fixed questions let you tell whether a retrieval change actually helped.", "qwen2.5:0.5b"),
    (12, "State the sample size and the hardware on the poster. Comparisons without either are treated as unsupported.", "qwen2.5:0.5b"),
]

cursor.executemany(
    "INSERT INTO assignment_summaries (assignment_id, ai_response, model) VALUES (?, ?, ?)",
    SUMMARIES,
)

RECOMMENDATIONS = [
    (1, "Microservices Architecture Patterns", "Reading", "Explains service decomposition and the diagrams the report asks for.", 1),
    (1, "Documenting Software Architectures", "Reading", "Gives a structure for architecture sections that maps onto the marking bullets.", None),
    (2, "Flask REST API Design Guide", "Guide", "Covers the resource-oriented routing the backend microservice needs.", 2),
    (2, "SQLite for Application Developers", "Reading", "Useful for the database microservice schema and seeding work.", 3),
    (3, "GitHub Actions in Practice", "Guide", "Walks through build, service probing and artefact upload steps.", None),
    (4, "Requirements Elicitation Techniques", "Reading", "Interview technique and question design for the transcript deliverable.", 4),
    (5, "Running Effective Retrospectives", "Video", "Shows how to turn discussion into owned improvement actions.", None),
    (6, "Database Normalisation Worked Examples", "Reading", "Step-by-step 1NF to 3NF decompositions with the reasoning shown.", 5),
    (7, "Reading Query Execution Plans", "Guide", "Needed to explain the before and after plans in the case study.", 6),
    (8, "WCAG 2.1 Quick Reference", "Reference", "The success criteria the component audit is graded against.", None),
    (8, "Keyboard Accessibility Testing", "Video", "Demonstrates the manual keyboard pass the task requires.", 7),
    (9, "Progressive Enhancement Revisited", "Reading", "Provides citable arguments for the essay's position.", None),
    (10, "OWASP Top 10 for LLM Applications", "Reference", "Source of the attack paths the threat model must cover.", 8),
    (11, "Retrieval Augmented Generation Explained", "Video", "Covers chunking and retrieval strategy choices for the prototype.", 9),
    (12, "Evaluating Language Models Fairly", "Reading", "Explains sample size and metric selection for the poster.", 10),
]

cursor.executemany(
    """
    INSERT INTO assignment_recommendations
        (assignment_id, title, resource_type, reason, source_resource_id)
    VALUES (?, ?, ?, ?, ?)
    """,
    RECOMMENDATIONS,
)


def remind(days_before_due, due_days):
    return (NOW + timedelta(days=due_days - days_before_due)).strftime("%Y-%m-%d %H:%M:%S")


REMINDERS = [
    (1, remind(3, 2), "Release 0 Technical Report is due in 2 days.", 0),
    (1, remind(7, 2), "Release 0 Technical Report drafting week starts now.", 1),
    (2, remind(3, 5), "Microservice Feature Implementation is due this week.", 0),
    (3, remind(3, 9), "CI/CD Workflow Evidence is due in 9 days.", 0),
    (4, remind(5, 12), "Book your Requirements Elicitation Interview slot.", 0),
    (5, remind(3, -3), "Sprint Retrospective Report was due - check your submission receipt.", 1),
    (6, remind(3, 4), "Normalisation Workshop is due in 4 days.", 0),
    (7, remind(7, 16), "Query Optimisation Case Study baselines should be captured by now.", 0),
    (8, remind(3, 7), "Accessible Component Library audit is due in a week.", 0),
    (9, remind(7, 21), "Progressive Enhancement Essay reading list due.", 0),
    (10, remind(2, 1), "Prompt Injection Threat Model is due tomorrow.", 0),
    (11, remind(14, 28), "Retrieval Augmented Generation Prototype evaluation set due.", 0),
    (12, remind(3, -9), "Model Evaluation Poster has been graded.", 1),
]

cursor.executemany(
    "INSERT INTO assignment_reminders (assignment_id, remind_at, message, acknowledged) VALUES (?, ?, ?, ?)",
    REMINDERS,
)

conn.commit()
conn.close()

print(
    f"Seeded {len(ASSIGNMENTS)} assignments, {len(SUMMARIES)} summaries, "
    f"{len(RECOMMENDATIONS)} recommendations and {len(REMINDERS)} reminders."
)
