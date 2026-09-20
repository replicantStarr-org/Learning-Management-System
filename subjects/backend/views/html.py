from html import escape


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<div class="alert alert-success mt-3" role="status">{escaped(text)}</div>'


def error(text):
    return f'<div class="alert alert-danger mt-3" role="alert">{escaped(text)}</div>'


TAG_COLOURS = (
    ("#0d6efd", "#ffffff"),
    ("#198754", "#ffffff"),
    ("#6f42c1", "#ffffff"),
    ("#d63384", "#ffffff"),
    ("#fd7e14", "#111111"),
    ("#087f8c", "#ffffff"),
)


def tag_badge(tag, extra_class=""):
    background, foreground = TAG_COLOURS[int(tag["tag_id"]) % len(TAG_COLOURS)]
    return (
        f'<span class="badge rounded-pill {escaped(extra_class)}" '
        f'style="background-color: {background}; color: {foreground};">'
        f'{escaped(tag["name"])}</span>'
    )


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
                <div class="card-body d-flex flex-column position-relative">
                    <span class="badge text-bg-primary mb-3 align-self-start">{escaped(subject['code'])}</span>
                    <h2 class="h5">{escaped(subject['name'])}</h2>
                    <div class="d-flex flex-wrap gap-1 position-absolute bottom-0 end-0 m-4 justify-content-end">
                        {''.join(tag_badge(tag) for tag in (subject.get('tags', [])[:2] if len(subject.get('tags', [])) > 3 else subject.get('tags', [])))}
                        {tag_badge({'tag_id': 0, 'name': '...'}) if len(subject.get('tags', [])) > 3 else ''}
                    </div>
                    <span class="text-primary fw-semibold">View subject <span aria-hidden="true">→</span></span>
                </div>
            </a>
        </div>
        """
        for subject in subjects
    )
    return f'<div class="row g-4">{cards}</div>'


def assigned_tags(subject, out_of_band=False):
    tags = subject.get("tags", [])
    content = "".join(tag_badge(tag) for tag in tags)
    if not content:
        content = '<span class="text-secondary small">No tags assigned</span>'
    oob = ' hx-swap-oob="outerHTML"' if out_of_band else ''
    return f'<div id="assigned-tags" class="d-flex flex-wrap gap-1"{oob}>{content}</div>'


def tag_options(subject, tags):
    subject_id = escaped(subject["subject_id"])
    selected = {tag["tag_id"] for tag in subject.get("tags", [])}
    selection_form_id = f"tag-selection-{subject_id}"
    controls = "".join(
        f'''
        <div class="d-flex align-items-center justify-content-between gap-2 py-1">
            <label class="form-check d-flex align-items-center gap-2 mb-0">
                <input class="form-check-input mt-0" type="checkbox" name="tag_ids"
                       form="{selection_form_id}" value="{escaped(tag['tag_id'])}" {'checked' if tag['tag_id'] in selected else ''}
                       onclick="event.stopPropagation();"
                       onchange="document.getElementById('{selection_form_id}').requestSubmit();">
                {tag_badge(tag)}
            </label>
            <details class="position-relative">
                <summary class="btn btn-sm text-secondary px-2 py-1 border-0 bg-transparent text-decoration-none list-unstyled"
                          aria-label="Actions for {escaped(tag['name'])}" style="cursor: pointer;"
                          onclick="event.stopPropagation(); closeOtherTagMenus(this.parentElement);">
                    <span aria-hidden="true">⋮</span>
                </summary>
                <div class="position-absolute end-0 top-100 bg-white border rounded shadow-sm p-2"
                     style="z-index: 1050; min-width: 18rem;" onclick="event.stopPropagation();">
                    <form hx-post="http://localhost:5001/tags/update" hx-target="#tag-manager" class="mb-2">
                        <input type="hidden" name="tag_id" value="{escaped(tag['tag_id'])}">
                        <input type="hidden" name="subject_id" value="{subject_id}">
                        <label class="visually-hidden" for="tag-name-{escaped(tag['tag_id'])}">Tag name</label>
                        <div class="input-group input-group-sm">
                            <input class="form-control" id="tag-name-{escaped(tag['tag_id'])}" name="name" value="{escaped(tag['name'])}" maxlength="120" required>
                            <button class="btn btn-outline-primary" type="submit">Save</button>
                        </div>
                    </form>
                    <button class="btn btn-sm btn-outline-danger w-100" type="button"
                            hx-post="http://localhost:5001/tags/delete" hx-target="#tag-manager"
                            hx-vals='{{"tag_id": "{escaped(tag['tag_id'])}", "subject_id": "{subject_id}"}}'
                            {f'hx-confirm="This tag is used by {int(tag.get("subject_count", 0))} subject(s). Delete it and remove it from all subjects?"' if int(tag.get("subject_count", 0)) else ''}>Delete</button>
                </div>
            </details>
        </div>
        '''
        for tag in tags
    )
    add_form = f'''
        <form hx-post="http://localhost:5001/tags" hx-target="#tag-options" class="border-top pt-2 mt-2">
            <input type="hidden" name="subject_id" value="{subject_id}">
            <label class="form-label small" for="new-tag-name">Add a tag</label>
            <div class="input-group input-group-sm">
                <input class="form-control" id="new-tag-name" name="name" maxlength="120" placeholder="Tag name" required>
                <button class="btn btn-outline-primary" type="submit">Add</button>
            </div>
        </form>
    '''
    return f'''
        <form id="{selection_form_id}" hx-post="http://localhost:5001/subjects/{subject_id}/tags" hx-target="#assigned-tags" hx-swap="outerHTML"></form>
        {controls or '<span class="text-secondary small">No tags available yet.</span>'}
        {add_form}
    '''


def tag_manager(subject, tags):
    if subject:
        subject_id = escaped(subject["subject_id"])
        return f'''
        <section id="tag-manager" class="card border-0 shadow-sm mb-4">
            <div class="card-body p-4">
                <div class="d-flex justify-content-between align-items-center gap-3">
                    <div>
                        <h2 class="h5 mb-1">Tags</h2>
                        {assigned_tags(subject)}
                    </div>
                    <button class="btn btn-outline-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false" onclick="closeAllTagMenus();">Manage tags</button>
                    <div class="dropdown-menu dropdown-menu-end p-3" style="min-width: 20rem; width: min(20rem, 90vw);">
                        <div id="tag-options">
                            {tag_options(subject, tags)}
                        </div>
                    </div>
                </div>
            </div>
        </section>
        '''
    return "".join(f'<div class="d-flex align-items-center gap-2 mb-2">{tag_badge(tag)} <span class="text-secondary small">{int(tag.get("subject_count", 0))} subject(s)</span></div>' for tag in tags)


def subject_detail(subject, tags):
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

        {tag_manager(subject, tags)}

        <div class="row g-4">
            <div class="col-lg-6">
                <section class="card border-0 shadow-sm h-100">
                    <div class="card-body p-4">
                        <h2 class="h5"><i class="bi bi-stars text-primary" aria-hidden="true"></i> AI summary</h2>
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


def subject_form(subject, tags):
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
    {tag_manager(subject, tags)}
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
