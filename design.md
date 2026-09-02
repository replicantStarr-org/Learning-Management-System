# Application Design

This code base is for a Learning Management System application.
This document lays out the high level design for this system.
The design describes the desired final state of the application rather than the current state.

The application is comprised of six microservices (five feature microservices + one shared access microservice).
Each microservice has three containers:
- A frontend container which is an nginx container, serves static web content
- A backend container which is flask application, functions as the backend
- A database container, also using flask to expose endpoints that manage a SQLite database

This gives a total 18 container application.

Microservices use a port assignment scheme,
the shared microservice the following ports:
- frontend: 3000
- backend: 5000
- database: 6000

Then each microservice uses the inclusive ranges 3001-3005, 5001-5005 and 6001-6005 respectively.
Ports are assigned with the nginx config for frontend (see [subject frontend config](subjects/frontend/nginx.conf)) and directly in `app.py` for flask apps

The containers communicate directly with each other through HTTP without any proxying.
To achieve this all backend applications use flask_cors to allow requests from any domain.
In addition to this, all containers should use `network_mode: host` to keep things simple, no need to define custom networks.

### Feature Microservices

A feature microservice is responsible for independently managing an entire feature within the learning management system.
The frontend of a feature microservice is standalone, meaning it serves as its own web page.
The intended tech stack for the frontend is pure HTML with HTMX and bootstrap css rather than any framework with custom rendering.
Although each feature should work as an independent web page and exist on a different domain, all pages together should still look as if they were part of one website.
To achieve this, shared components and themes should be placed in the `shared/` directory and consumed by all the frontend microservices.

Each microservice will have a `docker-compose.yml` that can be used to launch just that microservice and develop it.
The compose should be written in a way that makes it easily importable into a root compose file that will run the entire 18 container application.
The recommended file structure for a microservice is as follows:

```
.
├── backend
├── database
├── docker-compose.yml
└── frontend
```

The list of features for this application is given below, where created path and design are given:

- Subject Management - `subjects/` - [design doc](subjects/design.md)
- Learning Resource Manager - not yet created
- Assignments/Task Manager - not yet created
- Quiz/Knowledge Check Manager - `quizzes/` - [design doc](quizzes/design.md)
- Timetable Manager - not yet created


Features are intended to be independent but are permitted to integrate with other features by querying the database service from other features.
This querying must be done through the CRUD web API exposed by the database service, no direct querying is allowed.
Each database service exclusively owns its schema.

Each feature should have a `.yml` workflow file under `.github/workflows`, e.g. `subjects.yml`.
This workflow will be responsible for building and validating the microservice.
The workflow will run for pull requests which have changes under the path corresponding to that feature.
The jobs should be run on ubuntu-latest:
1. Build Images
    - Docker Compose build
2. Smoke Check
    - Start Docker Compose detatched
    - Probe the domain with a get request through curl for each service (database, backend, frontend - in that order), probing should have 8 attempts with 2 seconds waits in-between before failing. Timeouts should be used, only a response of 200 should be considered a success, only one attempt needs to succeed to proceed.
    - Optionally, run any non-functional requirement validation scripts if one exists within the feature folder
    - `docker compose down -v` with an `if: always()` clause for consistent teardown
3. Evidence Upload
    - Create JSON report with workflow name, run_id, commit_sha, branch and timestamp
    - Create a markdown report with similiar information and a url to the GH Run
    - Upload documents to the run

There should also be one `integration-ci.yml` that runs the joint docker compose and availability checks every domain
on every push/merge into the `main` branch + with an option to run it through manual dispatch on pull requests.

### Shared/Access Microservice

The shared microservice is used to manage access (accounts) and provide the entry point into the application.

Authentication will not be properly managed, instead it will exist in a demonstrative capacity.
The first time the user navigates to the application, they will be redirected to `/login`.
The login page will have a username and password, along with a link to a `/register` page instead.
The register page will have the same fields, and a link back to login, no additional information should be stored.
Any registered usernames + passwords will be stored in the database of the access microservice with password hashing.
Logging in will trigger a lookup in this database. If the login is successful a cookie with the username will be stored in the browser along with a creation date.

The backend for the access microservice will check for this cookie, and if the creation date was in the last 24h to determine if a user session is valid.
Otherwise, everywhere should redirect to `/login`.

> Note: This system makes it easy to impersonate any users, this is intentional, this is not intended to be proper security.
The application should also NOT implement any access control based on the user, all users have access to everything.
This is further reinforced with the split up domains model.
The other microservices will probably not even see this cookie and do not need to be login aware.

The shared microservice will serve as an index / table of contents for the application.
It will serve a `index.html` that represents the home page, its page will exist of links to the domains for the other features.
The body will contain descriptions of each feature, perhaps some icon, and a button (or the entire thing is a button) you can press to go to the frontend for that feature.
There will be also be a navbar with home, and all the features at the top.
This navbar will be defined in `shared/` and should be consistent across all six microservices, alongside the theme.


### Ollama Integration

A large aspect of this application is AI-integration.
This is achieved by running models locally through Ollama.
For this application, `qwen2.5:0.5b` will be used primarily,
if resources permit `deepseek-r1:8b` could be used for better responses.

Integration will be achived by running Ollama on the host.
An environment variable with the value of `http://localhost:11434/v1` will be passed to the backend through the compose file.
As the containers use host network mode, they should be able to access it natively through the API.
Microservices should implement an `ollama_client.py` that uses the `openai` library for requests and
defines functions for the AI services of that microservice.

For example, the subject microservice has a method for summarising subjects and another for answering a question about a subject.

All microservices should implement at least one AI feature.

