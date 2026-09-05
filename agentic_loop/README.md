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



