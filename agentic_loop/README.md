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


#### Endpoint Collector

The endpoint collector will collect a list of endpoints from the selected microservice.
The collector will search all files in the `backend` folder and use a regex to find endpoints.
If no endpoints are found, it will fail first.
Otherwise it will send a request to each endpoint, verifying no connection failures.
It will not fail based on the status code of the endpoint, as long as the endpoint responds quickly enough the collector will pass the test.
Instead, the result will be recorded and passed back as evidence to the models.

#### Application Architecture Collector

The collector for application architecture will verify the microservice has the required `backend`, `frontend` and `database` folders.
It will then check that database and backend services have an `app.py` and that the frontend service contains an `index.html`.
Finally it will check for the presence of the `docker-compose.yml` (or any `*compose.yml`) and verify it has three services, each one should have a substring of `frontend`, `backend` or `database`, no two services should have the same substring.

If these all pass, it will return a message saying that along with the content of the `docker-compose.yml` file.

#### DevOps Pipeline Collector

The DevOps pipeline collector will run checks against the workflow for the respective microservice.
It will also check against the artifacts for the specific microservice's latest run which can be found under `reports/` in the root of the repository.
There should be a hardcoded mapping for each microservice to a `.yml` file
along with a mapping for the respective folder under `reports/`.

The check against the workflow file should check for the presence of three jobs based on substring, a job for building the docker images (`*build*`), a job for running a smoke check (`*smoke*`) and final job for uploading the artifact (`*evidence*`).
It should also check that the workflow contains teardown with `docker-compose down -v` (or `--volumes`).

For the reports, it should identify the appropriate subfolders under `reports/`
and verify that there is at least one subfolder under that folder.
For example, the `reports/subjects` folder should have a subfolder under it which contains all the artifacts from a given run.
If the directory is empty, fail with a message here.
Otherwise for each directory there should be two files, one `*report.json` and another `*report.md`.
The `JSON` file should be checked for keys that contain the following substrings: `name`, `id`, `commit`, `branch` and `timestamp`.
Finally, the workflow file should be returned to the model for review.

### Prompts

Each area + microservice will also have prompts which serve as instructions for the models alongside the evidence provided by the collectors.
The prompts will be stored under `prompts/` in the root of the repository in a way that allows auto-discovery of the correct prompts for the task, rather than having to build out a manual mapping in code.

There also needs to be shared prompts for the following scenarios:
1. Reviewing the same area for different microservices, for example, all endpoint reviews should involve checking the endpoints follow CRUD/REST APIs formatting, regardless of which service it is. There can be one prompt for each area that is shared between microservices.
2. The agentic loop involves both a implementation and review agent. The instructions for a given area, and also a microservice can probably be shared between both of these. Then each of them will have a fragment added based on if they are implementation or review. This way you have a single prompt for each microservice that is used for both + a generic implementation prompt and review prompt that can be used for all combinations.

The following format will be used:

- `agents/`
    - `implementation_prompt.txt`
    - `review_prompt.txt`
- `areas/`
    - `database_prompt.txt`
    - `endpoint_prompt.txt`
    - `architecture_prompt.txt`
    - `devops_prompt.txt`
- `services/`
    - `access_prompt.txt`
    - `subjects_prompt.txt`
    - `quizzes_prompt.txt`
    - `resources_prompt.txt`
    - `timetable_prompt.txt`
    - `assignments_prompt.txt`

These prompts will be combined into a single prompt which will then be combined
with the evidence from the collectors to form the input into the model.
For example, if you are running the agentic loop againast the architecture of the access microservice and we are at the implementation agent phase.
The `implementation_prompt.txt`, `architecture_prompt.txt` and `access_prompt.txt` would be combined into the final prompt.
Appropriate format placeholders should be used to tell the agents which part they are reviewing along with other information to be injected or to put together the prompts in an appropriate way.


