import os
import sqlite3
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "quizzes.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS quiz_responses;")
cursor.execute("DROP TABLE IF EXISTS quiz_attempts;")
cursor.execute("DROP TABLE IF EXISTS quiz_answers;")
cursor.execute("DROP TABLE IF EXISTS quiz_questions;")
cursor.execute("DROP TABLE IF EXISTS quizzes;")

cursor.execute("""
CREATE TABLE quizzes (
    quiz_id INTEGER PRIMARY KEY,
    subject_id INTEGER,
    subject_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_update DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TRIGGER update_quiz_timestamp
AFTER UPDATE ON quizzes
FOR EACH ROW
BEGIN
    UPDATE quizzes
    SET last_update = CURRENT_TIMESTAMP
    WHERE quiz_id = OLD.quiz_id;
END;
""")

cursor.execute("""
CREATE TABLE quiz_questions (
    question_id INTEGER PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(quiz_id),
    question_text TEXT NOT NULL,
    explanation TEXT NOT NULL,
    question_order INTEGER NOT NULL
);
""")

cursor.execute("""
CREATE TABLE quiz_answers (
    answer_id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES quiz_questions(question_id),
    answer_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    answer_order INTEGER NOT NULL
);
""")

cursor.execute("""
CREATE TABLE quiz_attempts (
    attempt_id INTEGER PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(quiz_id),
    student_name TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL,
    ai_feedback TEXT,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);
""")

cursor.execute("""
CREATE TABLE quiz_responses (
    response_id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(attempt_id),
    question_id INTEGER NOT NULL REFERENCES quiz_questions(question_id),
    selected_answer_id INTEGER REFERENCES quiz_answers(answer_id),
    is_correct INTEGER NOT NULL DEFAULT 0
);
""")

# Quiz catalogue. subject_id/subject_name mirror the seed data in subjects/database/init_db.py
# (subjects own that schema; this feature only keeps a denormalised snapshot, per the
# cross-feature integration rule in the top-level design.md).
QUIZZES = [
    {
        "subject_id": 1, "subject_name": "ASD101 - Advanced Software Development",
        "title": "Advanced Software Development Fundamentals", "difficulty": "Easy",
        "description": "Test your understanding of core ASD concepts covered in the unit introduction.",
        "questions": [
            {
                "text": "Which of the following best describes a microservices architecture?",
                "explanation": "Microservices architecture decomposes an application into small, independently deployable services, each owning its own data and communicating over the network (e.g. HTTP/REST).",
                "answers": [
                    ("A single monolithic application deployed as one unit", False),
                    ("A collection of small, independently deployable services that communicate over a network", True),
                    ("A design pattern for writing recursive functions", False),
                    ("A database normalisation technique", False),
                ],
            },
            {
                "text": "What does 'CI/CD' stand for in a DevOps pipeline?",
                "explanation": "CI/CD stands for Continuous Integration and Continuous Delivery (or Deployment): automatically building, testing, and releasing code changes.",
                "answers": [
                    ("Continuous Integration / Continuous Delivery", True),
                    ("Code Inspection / Code Deployment", False),
                    ("Container Isolation / Container Distribution", False),
                    ("Client Interface / Client Data", False),
                ],
            },
            {
                "text": "In the Plan → Act → Observe → Adapt agentic workflow, what happens during the 'Observe' stage?",
                "explanation": "The Observe stage is where the agent collects the outcome or feedback from its most recent action so it can inform the next Adapt/Plan cycle.",
                "answers": [
                    ("The agent formulates a plan for the task", False),
                    ("The agent executes an action", False),
                    ("The agent gathers feedback or results from the action it just took", True),
                    ("The agent is deployed to production", False),
                ],
            },
            {
                "text": "Which of these is a non-functional requirement?",
                "explanation": "Non-functional requirements describe quality attributes such as performance, security, or scalability, rather than a specific feature.",
                "answers": [
                    ("The system must allow users to reset their password", False),
                    ("The system must respond to 95% of requests within 200ms", True),
                    ("The system must display a list of subjects", False),
                    ("The system must let a student submit a quiz attempt", False),
                ],
            },
        ],
    },
    {
        "subject_id": 1, "subject_name": "ASD101 - Advanced Software Development",
        "title": "Agile and Scrum Practices", "difficulty": "Medium",
        "description": "Check your knowledge of agile ceremonies and roles.",
        "questions": [
            {
                "text": "What is the primary purpose of a Sprint Retrospective?",
                "explanation": "The Sprint Retrospective is a team-only ceremony focused on continuous improvement of how the team works, not on the product itself.",
                "answers": [
                    ("To demo completed work to stakeholders", False),
                    ("To reflect on the past sprint and identify process improvements", True),
                    ("To estimate the size of backlog items", False),
                    ("To assign tasks to team members", False),
                ],
            },
            {
                "text": "Who is responsible for maintaining and prioritising the Product Backlog in Scrum?",
                "explanation": "The Product Owner owns the Product Backlog and is accountable for maximising the value of the product.",
                "answers": [
                    ("The Scrum Master", False),
                    ("The Development Team", False),
                    ("The Product Owner", True),
                    ("The project sponsor", False),
                ],
            },
            {
                "text": "What is a 'user story' in Agile development?",
                "explanation": "User stories capture requirements in simple, user-focused language, often in the form 'As a <role>, I want <goal>, so that <benefit>'.",
                "answers": [
                    ("A formal UML diagram", False),
                    ("A short, plain-language description of a feature from an end-user perspective", True),
                    ("A detailed technical design document", False),
                    ("A bug report", False),
                ],
            },
            {
                "text": "What does 'velocity' measure in Scrum?",
                "explanation": "Velocity is the amount of work (typically measured in story points) a team completes during a sprint, used to forecast future capacity.",
                "answers": [
                    ("The speed of the CI/CD pipeline", False),
                    ("The number of story points a team completes per sprint", True),
                    ("The number of bugs found in production", False),
                    ("The average response time of the API", False),
                ],
            },
        ],
    },
    {
        "subject_id": 2, "subject_name": "DBS102 - Database Systems",
        "title": "Relational Database Basics", "difficulty": "Easy",
        "description": "Fundamentals of relational databases: keys, integrity, and normalisation.",
        "questions": [
            {
                "text": "What is a primary key?",
                "explanation": "A primary key uniquely identifies each row in a table and cannot contain NULL or duplicate values.",
                "answers": [
                    ("A column that can contain duplicate values", False),
                    ("A column or set of columns that uniquely identifies each row in a table", True),
                    ("A key used to encrypt the database", False),
                    ("An index used only for sorting", False),
                ],
            },
            {
                "text": "Which SQL keyword is used to remove specific rows from a table?",
                "explanation": "DELETE removes specific rows matching a WHERE clause; DROP removes an entire table or database object.",
                "answers": [
                    ("REMOVE", False),
                    ("DROP", False),
                    ("DELETE", True),
                    ("TRUNCATE ROW", False),
                ],
            },
            {
                "text": "What does normalisation aim to reduce?",
                "explanation": "Normalisation organises data to minimise duplication and avoid anomalies when inserting, updating, or deleting records.",
                "answers": [
                    ("Query response time", False),
                    ("Data redundancy and update anomalies", True),
                    ("The number of tables in a schema", False),
                    ("The number of foreign keys", False),
                ],
            },
            {
                "text": "What is a foreign key used for?",
                "explanation": "A foreign key references the primary key of another table, enforcing referential integrity between related tables.",
                "answers": [
                    ("To speed up full text search", False),
                    ("To enforce a referential link between two tables", True),
                    ("To automatically back up a table", False),
                    ("To hash a password column", False),
                ],
            },
        ],
    },
    {
        "subject_id": 2, "subject_name": "DBS102 - Database Systems",
        "title": "SQL Query Practice", "difficulty": "Medium",
        "description": "Practice questions covering joins, aggregation, and transactions.",
        "questions": [
            {
                "text": "Which clause is used to filter grouped results in SQL?",
                "explanation": "WHERE filters rows before grouping; HAVING filters groups after GROUP BY has been applied.",
                "answers": [
                    ("WHERE", False),
                    ("HAVING", True),
                    ("FILTER", False),
                    ("GROUP", False),
                ],
            },
            {
                "text": "What does an INNER JOIN return?",
                "explanation": "An INNER JOIN returns only the rows where the join condition matches in both tables.",
                "answers": [
                    ("All rows from both tables regardless of match", False),
                    ("Only rows that have matching values in both tables", True),
                    ("Only rows from the left table", False),
                    ("A random sample of rows", False),
                ],
            },
            {
                "text": "Which function returns the number of rows in a result set?",
                "explanation": "COUNT() returns the number of rows that match a specified condition, or all rows if no condition is given.",
                "answers": [
                    ("SUM()", False),
                    ("COUNT()", True),
                    ("LEN()", False),
                    ("TOTAL()", False),
                ],
            },
            {
                "text": "What is the purpose of an SQL transaction?",
                "explanation": "Transactions ensure a group of operations are applied atomically, preserving consistency if any statement fails.",
                "answers": [
                    ("To visually format query output", False),
                    ("To group multiple statements so they succeed or fail as a single unit", True),
                    ("To create a new index", False),
                    ("To rename a column", False),
                ],
            },
            {
                "text": "Which statement adds a new column to an existing table?",
                "explanation": "ALTER TABLE ... ADD COLUMN is the standard SQL syntax for adding a new column to an existing table.",
                "answers": [
                    ("UPDATE TABLE", False),
                    ("ALTER TABLE ... ADD COLUMN", True),
                    ("CREATE COLUMN", False),
                    ("MODIFY TABLE ... NEW COLUMN", False),
                ],
            },
        ],
    },
    {
        "subject_id": 3, "subject_name": "WEB103 - Web Application Engineering",
        "title": "HTTP and Web Fundamentals", "difficulty": "Easy",
        "description": "Core concepts behind HTTP, status codes, and HTMX-driven frontends.",
        "questions": [
            {
                "text": "Which HTTP method is typically used to retrieve a resource without side effects?",
                "explanation": "GET requests are intended to be safe and idempotent, retrieving a resource without modifying server state.",
                "answers": [
                    ("POST", False),
                    ("GET", True),
                    ("DELETE", False),
                    ("PATCH", False),
                ],
            },
            {
                "text": "What HTTP status code indicates a resource was not found?",
                "explanation": "404 Not Found indicates the server could not find the requested resource.",
                "answers": [
                    ("200", False),
                    ("301", False),
                    ("404", True),
                    ("500", False),
                ],
            },
            {
                "text": "What does HTMX primarily allow you to do?",
                "explanation": "HTMX lets you trigger AJAX requests and swap HTML fragments using attributes like hx-get and hx-post, directly from markup.",
                "answers": [
                    ("Compile TypeScript to JavaScript", False),
                    ("Access modern browser features directly from HTML attributes, including AJAX requests", True),
                    ("Replace CSS with a new styling language", False),
                    ("Run a Python interpreter in the browser", False),
                ],
            },
            {
                "text": "What does CORS stand for?",
                "explanation": "CORS is a browser security mechanism that controls which origins are permitted to access resources on a server.",
                "answers": [
                    ("Cross-Origin Resource Sharing", True),
                    ("Client-Origin Request Security", False),
                    ("Cross-Object Rendering Standard", False),
                    ("Content Origin Rate Silencing", False),
                ],
            },
        ],
    },
    {
        "subject_id": 3, "subject_name": "WEB103 - Web Application Engineering",
        "title": "Web Security Essentials", "difficulty": "Hard",
        "description": "Common web vulnerabilities and how to defend against them.",
        "questions": [
            {
                "text": "What is Cross-Site Scripting (XSS)?",
                "explanation": "XSS occurs when untrusted input is rendered as executable script in a victim's browser, often due to missing output encoding.",
                "answers": [
                    ("A network-level denial-of-service attack", False),
                    ("An attack that injects malicious scripts into web pages viewed by other users", True),
                    ("A method of encrypting cookies", False),
                    ("A type of database index", False),
                ],
            },
            {
                "text": "What is the main defense against SQL injection?",
                "explanation": "Parameterised queries separate SQL code from user-supplied data, preventing attacker input from being interpreted as SQL.",
                "answers": [
                    ("Minifying JavaScript", False),
                    ("Using parameterised queries / prepared statements", True),
                    ("Disabling cookies", False),
                    ("Using HTTPS only", False),
                ],
            },
            {
                "text": "What does 'prompt injection' target in an AI-integrated application?",
                "explanation": "Prompt injection embeds malicious instructions inside data fed to an LLM, trying to override its original system prompt or safety rules.",
                "answers": [
                    ("The database connection pool", False),
                    ("Attempts to manipulate an LLM into ignoring its instructions via crafted input", True),
                    ("The TLS handshake", False),
                    ("The container network namespace", False),
                ],
            },
            {
                "text": "What is the principle of least privilege?",
                "explanation": "Least privilege limits the potential damage of a compromised account or component by minimising the access it is granted.",
                "answers": [
                    ("Granting all users administrator access by default", False),
                    ("Giving a user or process only the permissions it needs to perform its task", True),
                    ("Encrypting all data at rest", False),
                    ("Logging every request made to a service", False),
                ],
            },
        ],
    },
    {
        "subject_id": 4, "subject_name": "ALG204 - Algorithms and Complexity",
        "title": "Sorting and Searching Algorithms", "difficulty": "Medium",
        "description": "Time complexity and behaviour of common sorting and searching algorithms.",
        "questions": [
            {
                "text": "What is the average time complexity of binary search on a sorted array?",
                "explanation": "Binary search halves the search space on each comparison, giving it O(log n) time complexity.",
                "answers": [
                    ("O(n)", False),
                    ("O(log n)", True),
                    ("O(n log n)", False),
                    ("O(1)", False),
                ],
            },
            {
                "text": "What is the worst-case time complexity of quicksort?",
                "explanation": "Quicksort's worst case occurs with poor pivot choices (e.g. an already-sorted array with a naive pivot), degrading to O(n^2).",
                "answers": [
                    ("O(n log n)", False),
                    ("O(n)", False),
                    ("O(n^2)", True),
                    ("O(log n)", False),
                ],
            },
            {
                "text": "Which sorting algorithm is stable and has O(n log n) time complexity in all cases?",
                "explanation": "Merge sort guarantees O(n log n) performance in the best, average, and worst cases, and preserves the relative order of equal elements.",
                "answers": [
                    ("Quicksort", False),
                    ("Merge sort", True),
                    ("Selection sort", False),
                    ("Bubble sort", False),
                ],
            },
            {
                "text": "What data structure underlies an efficient priority queue implementation?",
                "explanation": "A binary heap supports O(log n) insertion and extraction of the minimum/maximum element, making it ideal for priority queues.",
                "answers": [
                    ("Linked list", False),
                    ("Heap", True),
                    ("Stack", False),
                    ("Hash map", False),
                ],
            },
            {
                "text": "What technique does dynamic programming rely on to improve efficiency?",
                "explanation": "Dynamic programming avoids redundant work by caching (memoising) results of overlapping subproblems.",
                "answers": [
                    ("Randomised pivot selection", False),
                    ("Storing and reusing solutions to overlapping subproblems", True),
                    ("Always choosing the locally optimal choice", False),
                    ("Recomputing every subproblem from scratch", False),
                ],
            },
        ],
    },
    {
        "subject_id": 5, "subject_name": "SWE205 - Software Architecture and Design",
        "title": "Software Architecture Patterns", "difficulty": "Medium",
        "description": "Common architectural styles and the trade-offs they involve.",
        "questions": [
            {
                "text": "What is the main benefit of the layered (n-tier) architecture pattern?",
                "explanation": "Layered architecture organises a system into layers (e.g. presentation, business logic, data), each with a distinct responsibility.",
                "answers": [
                    ("It eliminates the need for testing", False),
                    ("It separates concerns into distinct layers, improving maintainability", True),
                    ("It guarantees zero network latency", False),
                    ("It requires a single shared database table", False),
                ],
            },
            {
                "text": "In an event-driven architecture, how do components typically communicate?",
                "explanation": "Event-driven systems decouple producers and consumers by having them communicate through published events rather than direct calls.",
                "answers": [
                    ("Through direct synchronous function calls only", False),
                    ("By publishing and subscribing to events, often asynchronously", True),
                    ("Only through shared memory", False),
                    ("Through manual file transfers", False),
                ],
            },
            {
                "text": "What is a key trade-off of adopting a microservices architecture over a monolith?",
                "explanation": "Microservices gain deployment/scaling independence but introduce distributed-systems complexity such as network calls, versioning, and monitoring.",
                "answers": [
                    ("Simpler deployment with no added operational complexity", False),
                    ("Increased operational complexity in exchange for independent scalability and deployment", True),
                    ("Guaranteed lower latency for every request", False),
                    ("No need for network communication", False),
                ],
            },
            {
                "text": "What does the 'single responsibility principle' refer to?",
                "explanation": "The single responsibility principle states that a module should have one, and only one, reason to change.",
                "answers": [
                    ("A class or module should have only one reason to change", True),
                    ("A system should only have one developer", False),
                    ("A database should have only one table", False),
                    ("An API should only expose one endpoint", False),
                ],
            },
        ],
    },
    {
        "subject_id": 6, "subject_name": "SEC206 - Cybersecurity Fundamentals",
        "title": "Cybersecurity Basics", "difficulty": "Easy",
        "description": "Core security concepts every developer should know.",
        "questions": [
            {
                "text": "What does 'authentication' verify?",
                "explanation": "Authentication confirms who a user or system is, while authorisation determines what they are allowed to do.",
                "answers": [
                    ("What actions a user is allowed to perform", False),
                    ("The identity of a user or system", True),
                    ("The speed of a network connection", False),
                    ("The size of a database", False),
                ],
            },
            {
                "text": "What is the purpose of hashing a password before storing it?",
                "explanation": "Password hashing is a one-way transformation, meaning even if the database is compromised, the original password is not directly exposed.",
                "answers": [
                    ("To make the password easier to remember", False),
                    ("To avoid storing the plaintext password, so it can't be read directly if the database is breached", True),
                    ("To compress the password for storage efficiency", False),
                    ("To make the password reversible for support staff", False),
                ],
            },
            {
                "text": "What is a phishing attack?",
                "explanation": "Phishing uses social engineering, typically via email or messages, to trick victims into revealing credentials or sensitive data.",
                "answers": [
                    ("A brute-force attack against a database", False),
                    ("An attempt to trick a user into revealing sensitive information via deceptive messages", True),
                    ("A method of encrypting network traffic", False),
                    ("A type of firewall rule", False),
                ],
            },
            {
                "text": "What does the term 'attack surface' refer to?",
                "explanation": "The attack surface is the total set of exposed entry points (APIs, forms, ports, etc.) an attacker could target.",
                "answers": [
                    ("The physical size of a server room", False),
                    ("The sum of all points where an attacker could try to enter or extract data from a system", True),
                    ("The number of developers on a project", False),
                    ("The number of lines of code in a project", False),
                ],
            },
        ],
    },
    {
        "subject_id": 7, "subject_name": "CLO207 - Cloud Computing and DevOps",
        "title": "Cloud and DevOps Concepts", "difficulty": "Medium",
        "description": "Containerisation, CI/CD, and local vs. cloud deployment models.",
        "questions": [
            {
                "text": "What is the main advantage of containerisation (e.g. Docker)?",
                "explanation": "Containers bundle an application with its dependencies, ensuring consistent behaviour from a developer's machine through to production.",
                "answers": [
                    ("It guarantees infinite scalability", False),
                    ("It packages an application with its dependencies so it runs consistently across environments", True),
                    ("It removes the need for an operating system", False),
                    ("It automatically writes unit tests", False),
                ],
            },
            {
                "text": "What does Docker Compose primarily manage?",
                "explanation": "Docker Compose lets you define and run multi-container applications using a single docker-compose.yml file.",
                "answers": [
                    ("A single container's CPU limit", False),
                    ("Multi-container applications, defined declaratively in a YAML file", True),
                    ("Kubernetes cluster autoscaling", False),
                    ("Git branch merging", False),
                ],
            },
            {
                "text": "What is the purpose of a CI/CD pipeline's 'build' stage?",
                "explanation": "The build stage compiles or packages source code into an artifact (e.g. a Docker image) that can be tested and deployed.",
                "answers": [
                    ("To manually test the application in production", False),
                    ("To compile/package the application and produce a deployable artifact", True),
                    ("To delete old commits from git history", False),
                    ("To generate user documentation", False),
                ],
            },
            {
                "text": "In this project's local-vs-cloud deployment split, which services stay local-only?",
                "explanation": "Per the project's cloud deployment model, MCP, RAG, and Multi-Agent servers remain local-only, while AI-Mode and the approved LLM stay enabled in the cloud.",
                "answers": [
                    ("The frontend microservices", False),
                    ("MCP, RAG, and Multi-Agent servers", True),
                    ("The Ollama runtime entirely", False),
                    ("The relational database", False),
                ],
            },
        ],
    },
]

now = datetime.now(timezone.utc)


def ts(days_ago=0, hours_ago=0):
    return (now - timedelta(days=days_ago, hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


quiz_ids = []
question_rows_by_quiz = []  # list[list[{"question_id": int, "answers": [{"answer_id": int, "is_correct": bool}]}]]

for quiz in QUIZZES:
    cursor.execute(
        """
        INSERT INTO quizzes (subject_id, subject_name, title, description, difficulty, question_count, source, created_at, last_update)
        VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?)
        """,
        (
            quiz["subject_id"], quiz["subject_name"], quiz["title"], quiz["description"],
            quiz["difficulty"], len(quiz["questions"]), ts(days_ago=20), ts(days_ago=20),
        ),
    )
    quiz_id = cursor.lastrowid
    quiz_ids.append(quiz_id)

    questions = []
    for order, question in enumerate(quiz["questions"], start=1):
        cursor.execute(
            "INSERT INTO quiz_questions (quiz_id, question_text, explanation, question_order) VALUES (?, ?, ?, ?)",
            (quiz_id, question["text"], question["explanation"], order),
        )
        question_id = cursor.lastrowid
        answers = []
        for answer_order, (answer_text, is_correct) in enumerate(question["answers"], start=1):
            cursor.execute(
                "INSERT INTO quiz_answers (question_id, answer_text, is_correct, answer_order) VALUES (?, ?, ?, ?)",
                (question_id, answer_text, int(is_correct), answer_order),
            )
            answers.append({"answer_id": cursor.lastrowid, "is_correct": is_correct})
        questions.append({"question_id": question_id, "answers": answers})
    question_rows_by_quiz.append(questions)

# Seed quiz attempts + responses so quiz_attempts and quiz_responses each hold 10+ rows.
# quiz_index is the 0-based position of the quiz within QUIZZES above.
ATTEMPTS = [
    {"quiz_index": 0, "student_name": "Alice Nguyen", "outcomes": [True, True, True, True], "days_ago": 10},
    {"quiz_index": 0, "student_name": "Ben Carter", "outcomes": [True, False, True, False], "days_ago": 8},
    {"quiz_index": 1, "student_name": "Chloe Davis", "outcomes": [True, True, False, True], "days_ago": 7},
    {"quiz_index": 2, "student_name": "Daniel Kim", "outcomes": [True, True, True, True], "days_ago": 6},
    {"quiz_index": 2, "student_name": "Ben Carter", "outcomes": [False, True, True, True], "days_ago": 5},
    {"quiz_index": 3, "student_name": "Alice Nguyen", "outcomes": [True, False, True, True, False], "days_ago": 4},
    {"quiz_index": 4, "student_name": "Emma Wilson", "outcomes": [True, True, True, True], "days_ago": 9},
    {"quiz_index": 5, "student_name": "Daniel Kim", "outcomes": [False, True, False, True], "days_ago": 3},
    {"quiz_index": 6, "student_name": "Chloe Davis", "outcomes": [True, True, False, True, True], "days_ago": 2},
    {"quiz_index": 7, "student_name": "Emma Wilson", "outcomes": [True, False, True, True], "days_ago": 1},
    {"quiz_index": 8, "student_name": "Ben Carter", "outcomes": [True, True, True, False], "days_ago": 1},
    {"quiz_index": 9, "student_name": "Alice Nguyen", "outcomes": [True, True, True, True], "days_ago": 0},
]

for attempt in ATTEMPTS:
    quiz_id = quiz_ids[attempt["quiz_index"]]
    questions = question_rows_by_quiz[attempt["quiz_index"]]
    outcomes = attempt["outcomes"]
    score = sum(1 for outcome in outcomes if outcome)
    completed = ts(days_ago=attempt["days_ago"])

    cursor.execute(
        """
        INSERT INTO quiz_attempts (quiz_id, student_name, score, total_questions, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (quiz_id, attempt["student_name"], score, len(questions), completed, completed),
    )
    attempt_id = cursor.lastrowid

    for question, outcome in zip(questions, outcomes):
        chosen = next(a for a in question["answers"] if a["is_correct"] == outcome)
        cursor.execute(
            """
            INSERT INTO quiz_responses (attempt_id, question_id, selected_answer_id, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            (attempt_id, question["question_id"], chosen["answer_id"], int(outcome)),
        )

conn.commit()
conn.close()
