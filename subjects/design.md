# Subject Management Feature Design

This document details the design for the subject feature and the 3 associated microservices.
The design states the desired final state for the feature rather than current one as explained in the [application design](../design.md)

The subject management feature gives users the ability to view, create, update and delete subjects.
Additionally, AI can be used to ask questions about a given subject or to summarise the information about one.

### Functionality Breakdown

- View all subjects
- View details for a specific subject
    - The page for this should be navigated to from the previous feature. The default view should include bubble boxes that display the information about subjects. Clicking on this should take you to the details for that subject.
- Edit subject, a button on the view subject details page should take you to a page for editing that subject
- Create subject
    - This should be a button on the default view
- Delete subject, a button should be shown in the view subject details page
- Create subject, this should take you to a similar page as the edit subject page where you can fill in the fields for a new subject
- Ask a question about a subject and get an AI-generated response, there should be some loading to show the call is pending since LLM calls can take a while. If possible with HTMX, implement streaming for the text part of the response or a text animation after receiving the full response.
- Generate/view an AI summary about the subject
    - This should be generated on demand when viewing subject details
    - There should be the classic AI sparkles icon to indicate the 'subject summary' is AI generated
    - Summaries will be saved in the database and should be re-used
    - New summaries should be generated if the newest is older than a week or if the subjects last update timestamp is newer than the latest summary


Appropriate validation for the field lengths should be implemented, first as frontend input fields that prevent such inputs, and then repeated validation on the backend.

### Non-functional requirements (NFRs)

TODO

### Additional Notes

The subject feature should have a CI workflow as described in [the app design](../design.md).

NFRs have not yet been defined.
