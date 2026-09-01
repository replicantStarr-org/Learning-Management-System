from html import escape


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<div class="alert alert-success mt-3" role="status">{escaped(text)}</div>'


def error(text):
    return f'<div class="alert alert-danger mt-3" role="alert">{escaped(text)}</div>'


def subject_list(subjects):
    if not subjects:
        return (
            '<div class="text-center py-5">'
            '<h2 class="h4">No subjects yet</h2>'
            '<p class="text-secondary">Create your first subject to get started.</p>'
            '<a class="btn btn-primary" href="/create.html">Create a subject</a>'
            '</div>'
        )

    cards = "".join(
        f"""
        <div class="col-md-6 col-lg-4">
            <a class="card feature-card subject-card shadow-sm text-decoration-none text-reset"
               href="/subject.html?id={escaped(subject['subject_id'])}">
                <div class="card-body">
                    <span class="badge text-bg-primary mb-3">{escaped(subject['code'])}</span>
                    <h2 class="h5">{escaped(subject['name'])}</h2>
                    <span class="text-primary fw-semibold">View subject <span aria-hidden="true">→</span></span>
                </div>
            </a>
        </div>
        """
        for subject in subjects
    )
    return f'<div class="row g-4">{cards}</div>'


def subject_detail(subject):
    subject_id = escaped(subject["subject_id"])
    return f"""
    <article>
        <div class="d-flex flex-column flex-md-row justify-content-between gap-3 mb-4">
            <div>
                <span class="badge text-bg-primary mb-2">{escaped(subject['code'])}</span>
                <h1 class="display-6 fw-bold mb-2">{escaped(subject['name'])}</h1>
                <p class="text-secondary mb-0">Last updated {escaped(subject['last_update'])}</p>
            </div>
            <div class="d-flex align-items-start gap-2">
                <a class="btn btn-outline-primary" href="/edit.html?id={subject_id}">Edit</a>
                <button class="btn btn-outline-danger" type="button"
                        hx-post="http://localhost:5001/subjects/delete"
                        hx-vals='{{"subject_id": "{subject_id}"}}'
                        hx-confirm="Delete this subject permanently?">Delete</button>
            </div>
        </div>

        <div class="row g-3 mb-4">
            <div class="col-sm-4"><div class="bg-white rounded-4 shadow-sm p-3 h-100"><small class="text-secondary">Semester</small><p class="fw-semibold mb-0">{escaped(subject['semester'])}</p></div></div>
            <div class="col-sm-4"><div class="bg-white rounded-4 shadow-sm p-3 h-100"><small class="text-secondary">Coordinator</small><p class="fw-semibold mb-0">{escaped(subject['coordinator'])}</p></div></div>
            <div class="col-sm-4"><div class="bg-white rounded-4 shadow-sm p-3 h-100"><small class="text-secondary">Status</small><p class="fw-semibold mb-0">{escaped(subject['status'])}</p></div></div>
        </div>

        <section class="card border-0 shadow-sm mb-4">
            <div class="card-body p-4">
                <h2 class="h5">Description</h2>
                <p class="mb-0 preserve-lines">{escaped(subject['description'])}</p>
            </div>
        </section>

        <div class="row g-4">
            <div class="col-lg-6">
                <section class="card border-0 shadow-sm h-100">
                    <div class="card-body p-4">
                        <h2 class="h5"><i class="bi bi-stars text-primary" aria-hidden="true"></i> AI summary</h2>
                        <p class="text-secondary">A current saved summary is reused; an outdated one is regenerated automatically.</p>
                        <div id="summary-result" aria-live="polite"
                             hx-post="http://localhost:5001/subjects/{subject_id}/summary"
                             hx-trigger="load" hx-swap="innerHTML">
                            <div class="d-flex align-items-center gap-2 py-3 text-secondary" role="status">
                                <span class="spinner-border spinner-border-sm text-primary" aria-hidden="true"></span>
                                <span>Loading AI summary…</span>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
            <div class="col-lg-6">
                <section class="card border-0 shadow-sm h-100">
                    <div class="card-body p-4">
                        <h2 class="h5"><i class="bi bi-chat-dots text-primary" aria-hidden="true"></i> Ask about this subject</h2>
                        <p class="text-secondary">Ask a question using the information in this subject.</p>
                        <form hx-post="http://localhost:5001/subjects/questions" hx-target="#question-result" hx-indicator="#question-loading">
                            <input type="hidden" name="subject_id" value="{subject_id}">
                            <label class="form-label" for="question">Question</label>
                            <textarea class="form-control mb-3" id="question" name="question" rows="3" maxlength="1000" required></textarea>
                            <button class="btn btn-primary" type="submit">Ask AI</button>
                            <span class="htmx-indicator ms-2" id="question-loading" role="status"><span class="spinner-border spinner-border-sm"></span> Thinking…</span>
                        </form>
                        <div id="question-result" aria-live="polite"></div>
                    </div>
                </section>
            </div>
        </div>
    </article>
    """


def subject_form(subject):
    return f"""
    <form hx-post="http://localhost:5001/subjects/update" hx-target="#form-result">
        <input type="hidden" name="subject_id" value="{escaped(subject['subject_id'])}">
        {_subject_fields(subject)}
        <div class="d-flex gap-2">
            <button class="btn btn-primary" type="submit">Save changes</button>
            <a class="btn btn-outline-secondary" href="/subject.html?id={escaped(subject['subject_id'])}">Cancel</a>
        </div>
        <div id="form-result" aria-live="polite"></div>
    </form>
    """


def _subject_fields(subject=None):
    values = subject or {}
    fields = (
        ("code", "Code", 20, "CLS001"),
        ("name", "Name", 120, "Generic Subject Name"),
        ("semester", "Semester", 60, "Spring"),
        ("coordinator", "Coordinator", 120, "Dr. Jane Doe"),
        ("status", "Status", 60, "Open"),
    )
    controls = "".join(
        f"""
        <div class="col-md-6">
            <label class="form-label" for="{name}">{label}</label>
            <input class="form-control" id="{name}" name="{name}" maxlength="{limit}"
                   value="{escaped(values.get(name, ''))}" placeholder="{placeholder}" required>
        </div>
        """
        for name, label, limit, placeholder in fields
    )
    return f"""
    <div class="row g-3 mb-3">{controls}</div>
    <div class="mb-4">
        <label class="form-label" for="description">Description</label>
        <textarea class="form-control" id="description" name="description" rows="6" maxlength="5000" required>{escaped(values.get('description', ''))}</textarea>
        <div class="form-text">Maximum 5,000 characters.</div>
    </div>
    """


def summary_result(summary):
    source = "Cached summary" if summary.get("reused") else "Newly generated summary"
    return f"""
    <div class="alert alert-primary mb-0 ai-result">
        <p class="fw-semibold mb-1"><i class="bi bi-stars" aria-hidden="true"></i> {source}</p>
        <p class="mb-2 preserve-lines">{escaped(summary['ai_response'])}</p>
        <small class="text-secondary">Summary timestamp: {escaped(summary['timestamp'])}</small>
    </div>
    """


def question_result(result):
    return f"""
    <div class="alert alert-primary mt-3 ai-result">
        <p class="fw-semibold mb-1">Answer</p>
        <p class="mb-0 preserve-lines">{escaped(result['answer'])}</p>
    </div>
    """
