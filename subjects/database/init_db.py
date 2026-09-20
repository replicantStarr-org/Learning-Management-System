import os
import sqlite3

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "subjects.db")

os.makedirs(DATA_DIR, exist_ok=True)

conn = sqlite3.connect(
    DATABASE_NAME
)

cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS subject_tags;")
cursor.execute("DROP TABLE IF EXISTS subject_ai_summaries;")
cursor.execute("DROP TABLE IF EXISTS tags;")
cursor.execute("DROP TABLE IF EXISTS subjects;")

cursor.execute("""
CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    semester TEXT NOT NULL,
    coordinator TEXT NOT NULL,
    status TEXT NOT NULL,
    last_update DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")


cursor.execute("""
CREATE TRIGGER update_subject_timestamp 
AFTER UPDATE ON subjects
FOR EACH ROW
BEGIN
    UPDATE subjects 
    SET last_update = CURRENT_TIMESTAMP 
    WHERE subject_id = OLD.subject_id;
END;
""")

cursor.execute("""
CREATE TABLE subject_ai_summaries (
    summary_id INTEGER PRIMARY KEY,
    ai_response TEXT NOT NULL,
    subject_id INTEGER REFERENCES subjects(subject_id),
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE tags (
    tag_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
""")

cursor.execute("""
CREATE TABLE subject_tags (
    subject_id INTEGER NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (subject_id, tag_id)
);
""")

tags = [("Core",), ("Elective",), ("Practical",)]
cursor.executemany("INSERT INTO tags (name) VALUES (?)", tags)

subjects = [
    # this description was taken from https://coursehandbook.uts.edu.au/subject/2026/41026
    ("ASD101", "Advanced Software Development", "This subject advances your understanding of software development, such as the design, development, and evaluation of a complex software system that fulfills specific functional and non-functional requirements. You will work in highly autonomous teams that, while supervised and directed, take full responsibility for the project and delivery of the expected outcomes. The subject focuses on professional practices including team management, project planning, and all key software development processes. You will also make and justify informed design decisions, enhancing your capability to deliver sound software solutions.", "Spring", "Dr. Georges", "Full"),
    # acknowledgement: the following data rows were created with generative AI 
    ("DBS102", "Database Systems", "This subject introduces the principles and practices required to design, implement, query, and maintain reliable database systems. You will examine relational modeling, normalization, indexing, transactions, concurrency control, and recovery while developing practical SQL skills against realistic datasets. The subject also considers data integrity, security, performance tuning, and the trade-offs involved in selecting database technologies. Through a substantial design and implementation task, you will learn to translate business requirements into maintainable schemas and explain the technical decisions behind a robust data solution.", "Spring", "Prof. Amelia Hart", "Full"),
    ("WEB103", "Web Application Engineering", "This subject explores the engineering of modern web applications from initial requirements through deployment and maintenance. You will develop accessible, responsive interfaces and connect them to server-side services, persistent storage, and external APIs. Topics include HTTP, web security, validation, authentication, testing, version control, and deployment automation, with emphasis on maintainability and user experience. Practical workshops and a project will help you compare architectural approaches, identify common failure modes, and produce a complete web application that meets clearly defined functional and non-functional requirements.", "Autumn", "Dr. Nina Patel", "Open"),
    ("ALG204", "Algorithms and Complexity", "This subject develops the analytical skills needed to select and justify efficient algorithms for computational problems. You will study searching, sorting, graph algorithms, greedy methods, divide-and-conquer strategies, dynamic programming, and data structures that support them. Mathematical reasoning is combined with implementation and experimentation so that you can evaluate time and space complexity rather than relying only on observed performance. By the end of the subject, you will be able to recognize computational trade-offs, prove key properties of solutions, and communicate algorithmic choices clearly in technical documentation.", "Autumn", "Dr. Samuel Okafor", "Full"),
    ("SWE205", "Software Architecture and Design", "This subject examines how large software systems are structured so that they remain understandable, adaptable, secure, and dependable as requirements change. You will investigate architectural styles, modularity, interfaces, domain modeling, event-driven systems, distributed components, and quality attributes such as scalability and resilience. Design patterns are considered in context rather than as isolated recipes, and you will practice documenting decisions with appropriate diagrams and rationale. The assessment work requires you to evaluate competing architectures and evolve a design in response to realistic technical and organizational constraints.", "Spring", "Prof. Lucas Meyer", "Closed for enrolment"),
    ("SEC206", "Cybersecurity Fundamentals", "This subject provides a practical foundation in protecting software, systems, networks, and data from accidental and deliberate threats. You will study security principles, threat modeling, identity and access management, cryptography concepts, secure coding, network defense, vulnerability assessment, and incident response. Labs and case studies demonstrate how weaknesses arise across the development and operational lifecycle, while also addressing ethics, privacy, and responsible disclosure. You will finish with the ability to assess risk, recommend proportionate controls, and explain security findings to both technical and non-technical stakeholders.", "Winter", "Dr. Helen Brooks", "Full"),
    ("CLO207", "Cloud Computing and DevOps", "This subject introduces the concepts and practices used to build, deploy, and operate applications on cloud platforms. You will work with virtualized infrastructure, containers, managed services, automated pipelines, observability, configuration management, and infrastructure as code. Particular attention is given to reliability, cost awareness, security, and the collaboration between development and operations teams. Through an applied project, you will design a deployment workflow, monitor a running service, respond to simulated failures, and justify how your operational choices support repeatable and sustainable software delivery.", "Winter", "Eng. Marcus Liu", "Full"),
    ("AI208", "Artificial Intelligence and Machine Learning", "This subject introduces core ideas behind artificial intelligence and machine learning, combining conceptual understanding with responsible practical application. You will explore supervised and unsupervised learning, feature preparation, model evaluation, optimization, and the limitations of statistical predictions. Assignments emphasize reproducible experiments, appropriate baselines, interpretation of results, and the effect of data quality on model behavior. Ethical issues including bias, privacy, transparency, and the social consequences of automation are integrated throughout, enabling you to build and critically assess a small machine learning solution rather than treating a model as a black box.", "Spring", "Dr. Sofia Alvarez", "Closed for enrolment"),
    ("HCI209", "Human-Computer Interaction", "This subject focuses on designing interactive systems that are useful, usable, accessible, and satisfying for the people who rely on them. You will learn to investigate user needs, frame problems, create prototypes, apply interaction design principles, and evaluate interfaces through observation and structured usability methods. The subject covers inclusive design, information architecture, visual hierarchy, cognitive considerations, and iterative feedback. A design project will require you to connect research evidence to interface decisions and communicate how your proposed solution improves the experience for a clearly identified group of users.", "Autumn", "Dr. Priya Raman", "Full"),
    ("NET210", "Computer Networks", "This subject explains how digital devices exchange information across local and global networks. You will study layered network models, addressing, routing, transport protocols, wireless communication, DNS, HTTP, and the practical causes of delay, loss, and congestion. Laboratory exercises provide experience with packet inspection, network configuration, and troubleshooting, while security considerations show how protocols can be misused or defended. You will develop the ability to reason from observed network behavior, design a small reliable network, and document solutions to connectivity and performance problems.", "Autumn", "Prof. Daniel Reed", "Full"),
    ("MOB211", "Mobile Application Development", "This subject covers the design and implementation of applications for mobile devices, with attention to constrained resources and varied user contexts. You will explore platform conventions, navigation, lifecycle management, local persistence, remote services, notifications, permissions, and responsive layouts. Testing on different screen sizes and connectivity conditions is used to reveal issues that are not obvious in a desktop environment. The project emphasizes clean architecture, accessibility, privacy-conscious handling of device data, and a polished user experience supported by clear technical documentation and evaluation evidence.", "Winter", "Dr. Elena Rossi", "Full"),
    ("TES212", "Software Testing and Quality Assurance", "This subject develops systematic approaches for finding defects and building confidence in software behavior. You will study test planning, unit and integration testing, system and acceptance testing, black-box and white-box techniques, property-based testing, regression strategies, and test automation. Quality is considered broadly, including performance, security, usability, maintainability, and reliability. You will learn to prioritize testing based on risk, interpret results responsibly, and integrate quality activities into a development workflow so that testing informs design and delivery instead of being treated as a final inspection step.", "Spring", "Dr. Michael Chen", "Full"),
    ("PRJ213", "Project Management for Computing", "This subject examines the planning, coordination, and leadership practices needed to deliver computing projects in uncertain and changing environments. You will work with scope definition, estimation, scheduling, risk management, stakeholder communication, budgeting, quality planning, and iterative delivery methods. Case studies highlight how technical decisions interact with organizational priorities and team dynamics. In a practical project setting, you will maintain a delivery plan, track progress against evidence, respond to changing requirements, and reflect on how collaboration and professional communication affect the likelihood of a successful outcome.", "Winter", "Prof. Rebecca Stone", "Open"),
    ("DAT214", "Data Analytics and Visualization", "This subject teaches a structured process for turning raw data into useful and defensible insight. You will practice data cleaning, exploratory analysis, statistical reasoning, feature selection, and the communication of uncertainty using appropriate visualizations. Emphasis is placed on reproducible workflows, identifying misleading interpretations, and selecting charts that match the question and audience. You will complete an analysis using a realistic dataset, explain the assumptions and limitations of your methods, and present findings in a way that supports informed decisions without overstating what the data can demonstrate.", "Autumn", "Dr. Aisha Khan", "Full"),
    ("OS215", "Operating Systems", "This subject explores the mechanisms that allow operating systems to manage hardware and provide dependable services to applications. Topics include processes and threads, scheduling, synchronization, memory management, file systems, input and output, virtualization, and protection. Practical exercises allow you to observe system behavior and implement selected components, reinforcing the relationship between abstract abstractions and resource constraints. You will learn to diagnose concurrency and performance problems, reason about isolation and failure, and explain how operating-system design influences the reliability of software running on top of it.", "Spring", "Dr. Thomas Weber", "Open"),

]

cursor.executemany("""
INSERT INTO subjects (
    code,
    name,
    description,
    semester,
    coordinator,
    status
)
VALUES (?, ?, ?, ?, ?, ?)
""", subjects)


conn.commit()
conn.close()

