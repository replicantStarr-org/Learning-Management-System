## Agentic Loop

The agentic loop takes artifiacts, code and prompts from the repository.
It suggests improvements by first running inputs through an implementation model and
then refining, rejecting and filtering them with a review model.

The agentic loop supports review of four different areas:
- Database
- Endpoint Implementation
- Application Architecture
- DevOps Pipeline

To keep the review focused,
you must also choose which microservice the review is for.
This includes the five feature microservice + the shared access microservice:
- Shared home page - `access/`
- Subjects Manager - `subjects/`
- Assignment Manager - `assignments/`
- Learning Resource Manager - `learning-resource-manager/`
- Quiz Manager - `quizzes/`
- Timetable Manager - `timetable/`

> Note: The above paths are given relative to the repository root. (`../` relative to this file)


### Collectors

Collectors are used to collect the concrete parts of the implementation, aka, evidence, that will be reviewed by the model.
There is a collector for each area the agentic loop supports.
Each collector can also observe and perform validation on the data it collects.
This allows us to introduce some determinstic guardrails into the agentic workflow.
This validation can also be used to short circuit the agentic loop at the observe phase.
To achieve this, each collector returns a `tuple[bool, str]`.
The boolean represents if validation passed,
with the string being the evidence and other applicable information to be passed the model or output to the screen.
The collector for each area is described in detail below.

#### Database Collector

The database collector will take the `init_db.py` (may be named something differently, find a python file with init + `db` or `data`, also collect any `.sql` files in the folder) from the respective `database` container and do the following:

1. Copy the file to a temporary directory
2. Use `runpy` to run the file in the current context
3. Verify that a `.db` file was created in the temporary directory, either as a direct child or in a nested folder
4. Use a regex to extract all `CREATE TABLE` statements from selected files
5. `SELECT COUNT(*)` from all matched tables named, verify at least 5 seeded entries for each table
6. Return the result of this check + all `CREATE TABLE` statements as a string


####



### Prompts


### TODO

- describe what is collected and reviewed for each area
- prompt and report layouts
    - each microservice has its own prompts for review
    - shared prompts for things that must always be true, i.e CRUD endpoints
- how each collector works, what it should collect, i.e endpoints that can be reviewed for CRUD etc
- file structure for prompts and auto-discovery
- auto-download artifacts for workflow runs
- database collector inputs init_db script and reviews that






