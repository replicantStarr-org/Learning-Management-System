from html import escape

BACKEND_BASE = "http://localhost:5004"
FRONTEND_BASE = "http://localhost:3004"


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<div class="alert alert-success mt-3" role="status">{escaped(text)}</div>'


def generated_quiz_message(quiz):
    return f"""
    <div class="alert alert-success mt-3 d-flex justify-content-between align-items-center flex-wrap gap-2" role="status">
        <span>Generated &quot;{escaped(quiz['title'])}&quot; with {quiz['question_count']} questions.</span>
        <a class="btn btn-sm btn-success" href="/quiz.html?id={quiz['quiz_id']}">
            Go to quiz <i class="bi bi-arrow-right ms-1"></i>
        </a>
    </div>
    """


def subject_options(subjects):
    if not subjects:
        return '<option value="" disabled selected>No subjects available - check the Subject Management service</option>'

    options = "".join(
        f'<option value="{escaped(subject["subject_id"])}">{escaped(subject["code"])} - {escaped(subject["name"])}</option>'
        for subject in subjects
    )
    return f'<option value="" disabled selected>Choose a subject…</option>{options}'


def error(text):
    return f'<div class="alert alert-danger mt-3" role="alert">{escaped(text)}</div>'


DIFFICULTY_BADGE_CLASSES = {
    "Easy": "bg-success-subtle text-success-emphasis border border-success-subtle",
    "Medium": "bg-warning-subtle text-warning-emphasis border border-warning-subtle",
    "Hard": "bg-danger-subtle text-danger-emphasis border border-danger-subtle",
}


def _difficulty_badge(difficulty):
    classes = DIFFICULTY_BADGE_CLASSES.get(difficulty, "text-bg-primary")
    return f'<span class="badge {classes}">{escaped(difficulty)}</span>'


def _source_badge(quiz):
    if quiz.get("source") == "ai_generated":
        return '<span class="badge text-bg-primary"><i class="bi bi-stars me-1" aria-hidden="true"></i>AI-generated</span>'
    return '<span class="badge text-bg-light text-secondary">Manual</span>'


def quiz_list(quizzes):
    if not quizzes:
        return (
            '<div class="text-center py-5">'
            '<h2 class="h4">No quizzes yet</h2>'
            '<p class="text-secondary">Generate one with AI or create one manually to get started.</p>'
            f'<a class="btn btn-primary" href="/generate.html">Generate with AI</a>'
            '</div>'
        )

    cards = "".join(
        f"""
        <div class="col-md-6 col-lg-4">
            <a class="card feature-card subject-card shadow-sm text-decoration-none text-reset"
               href="/quiz.html?id={escaped(quiz['quiz_id'])}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        {_difficulty_badge(quiz['difficulty'])}
                        {_source_badge(quiz)}
                    </div>
                    <h2 class="h5">{escaped(quiz['title'])}</h2>
                    <p class="text-secondary small mb-2">{escaped(quiz['subject_name'])}</p>
                    <span class="text-primary fw-semibold">{quiz['question_count']} questions <span aria-hidden="true">→</span></span>
                </div>
            </a>
        </div>
        """
        for quiz in quizzes
    )
    return f'<div class="row g-4">{cards}</div>'


def _answer_options(question):
    return "".join(
        f"""
        <div class="form-check mb-2">
            <input class="form-check-input" type="radio" name="q_{question['question_id']}"
                   id="a_{answer['answer_id']}" value="{answer['answer_id']}" required>
            <label class="form-check-label" for="a_{answer['answer_id']}">{escaped(answer['answer_text'])}</label>
        </div>
        """
        for answer in question["answers"]
    )


def _quiz_header(quiz):
    quiz_id = escaped(quiz["quiz_id"])
    return f"""
    <div class="d-flex flex-column flex-md-row justify-content-between gap-3 mb-4">
        <div>
            <span class="mb-2 d-inline-block">{_difficulty_badge(quiz['difficulty'])}</span>
            <span class="mb-2 d-inline-block">{_source_badge(quiz)}</span>
            <h1 class="display-6 fw-bold mb-2">{escaped(quiz['title'])}</h1>
            <p class="text-secondary mb-0">{escaped(quiz['subject_name'])}</p>
        </div>
        <div class="d-flex align-items-start gap-2">
            <a class="btn btn-outline-primary" href="/edit.html?id={quiz_id}">Edit</a>
            <button class="btn btn-outline-danger" type="button"
                    hx-post="{BACKEND_BASE}/quizzes/delete"
                    hx-vals='{{"quiz_id": "{quiz_id}"}}'
                    hx-confirm="Delete this quiz permanently?">Delete</button>
        </div>
    </div>
    <p class="mb-4">{escaped(quiz['description'])}</p>
    """


def _history_button(quiz):
    return f"""
    <button class="btn btn-outline-secondary" type="button"
            hx-get="{BACKEND_BASE}/quizzes/{quiz['quiz_id']}/attempts" hx-target="#quiz-view">
        <i class="bi bi-clock-history me-1"></i> View past attempts
    </button>
    """


def quiz_detail(quiz):
    header = _quiz_header(quiz)

    if not quiz["questions"]:
        return f"""
        {header}
        <div class="alert alert-warning">This quiz has no questions yet.
            <a href="/edit.html?id={quiz['quiz_id']}">Add some</a>.
        </div>
        {_history_button(quiz)}
        """

    questions_html = "".join(
        f"""
        <fieldset class="mb-4">
            <legend class="h6">{index + 1}. {escaped(question['question_text'])}</legend>
            {_answer_options(question)}
        </fieldset>
        """
        for index, question in enumerate(quiz["questions"])
    )

    return f"""
    {header}
    <section class="card border-0 shadow-sm mb-4">
        <div class="card-body p-4">
            <form hx-post="{BACKEND_BASE}/quizzes/{quiz['quiz_id']}/attempts" hx-target="#quiz-view" hx-indicator="#attempt-loading">
                <input type="hidden" id="student_name" name="student_name">
                {questions_html}
                <button class="btn btn-primary" type="submit">Submit answers</button>
                <span class="htmx-indicator ms-2" id="attempt-loading" role="status"><span class="spinner-border spinner-border-sm"></span> Grading…</span>
            </form>
        </div>
    </section>
    {_history_button(quiz)}
    """


def attempt_result(attempt):
    rows = "".join(
        f"""
        <li class="list-group-item list-group-item-{'success' if response['is_correct'] else 'danger'}">
            <p class="fw-semibold mb-1">{escaped(response['question_text'])}</p>
            <p class="mb-1">Your answer: {escaped(response['selected_answer_text'])}
                {'<i class="bi bi-check-lg"></i>' if response['is_correct'] else '<i class="bi bi-x-lg"></i>'}</p>
            {'' if response['is_correct'] else (
                f"<p class='mb-1'>Correct answer: {escaped(response['correct_answer_text'])}</p>"
                f"<p class='mb-0 fst-italic'>{escaped(response['explanation'])}</p>"
            )}
        </li>
        """
        for response in attempt["responses"]
    )

    return f"""
    <section class="card border-0 shadow-sm mb-4">
        <div class="card-body p-4">
            <h1 class="h4">Your score: {attempt['score']} / {attempt['total_questions']}</h1>
            <ul class="list-group list-group-flush my-3">{rows}</ul>
            <button class="btn btn-primary" type="button"
                    hx-post="{BACKEND_BASE}/attempts/{attempt['attempt_id']}/feedback"
                    hx-target="#ai-feedback-result" hx-indicator="#feedback-loading">
                <i class="bi bi-stars me-1"></i> Get AI feedback on my mistakes
            </button>
            <span class="htmx-indicator ms-2" id="feedback-loading" role="status"><span class="spinner-border spinner-border-sm"></span> Thinking…</span>
            <div id="ai-feedback-result" aria-live="polite"></div>
        </div>
    </section>
    <a class="btn btn-outline-secondary" href="/">Back to all quizzes</a>
    """


def attempts_list(quiz, attempts):
    if not attempts:
        body = '<p class="text-secondary">No attempts have been made on this quiz yet.</p>'
    else:
        rows = "".join(
            f"""
            <li class="list-group-item d-flex justify-content-between align-items-center flex-wrap gap-2">
                <span>{escaped(attempt['student_name'])}</span>
                <span class="badge text-bg-primary rounded-pill">{attempt['score']}/{attempt['total_questions']}</span>
                <small class="text-secondary">{escaped(attempt['completed_at'] or attempt['started_at'])}</small>
            </li>
            """
            for attempt in attempts
        )
        body = f'<ul class="list-group list-group-flush mb-3">{rows}</ul>'

    return f"""
    <h1 class="h4 mb-3">{escaped(quiz['title'])} &mdash; attempt history</h1>
    {body}
    <button class="btn btn-outline-secondary" type="button"
            hx-get="{BACKEND_BASE}/quizzes/{quiz['quiz_id']}" hx-target="#quiz-view">Back to quiz</button>
    """


def feedback_result(attempt):
    return f"""
    <div class="alert alert-primary mt-3">
        <p class="fw-semibold mb-1"><i class="bi bi-stars" aria-hidden="true"></i> AI feedback</p>
        <p class="mb-0 preserve-lines">{escaped(attempt['ai_feedback'])}</p>
    </div>
    """


def _quiz_fields(quiz=None):
    values = quiz or {}
    difficulty_options = "".join(
        f'<option{" selected" if values.get("difficulty") == option else ""}>{option}</option>'
        for option in ("Easy", "Medium", "Hard")
    )
    return f"""
    <div class="row g-3 mb-3">
        <div class="col-md-6">
            <label class="form-label" for="title">Title</label>
            <input class="form-control" id="title" name="title" maxlength="150"
                   value="{escaped(values.get('title', ''))}" required>
        </div>
        <div class="col-md-6">
            <label class="form-label" for="difficulty">Difficulty</label>
            <select class="form-select" id="difficulty" name="difficulty">{difficulty_options}</select>
        </div>
    </div>
    <div class="mb-4">
        <label class="form-label" for="description">Description</label>
        <textarea class="form-control" id="description" name="description" rows="3" maxlength="2000" required>{escaped(values.get('description', ''))}</textarea>
    </div>
    """


def _answer_summary_row(answer):
    check = ' <i class="bi bi-check-lg text-success"></i>' if answer["is_correct"] else ""
    return f"<li>{escaped(answer['answer_text'])}{check}</li>"


def quiz_edit_form(quiz):
    quiz_id = escaped(quiz["quiz_id"])
    questions_html = "".join(
        f"""
        <li class="list-group-item">
            <p class="fw-semibold mb-1">{index + 1}. {escaped(question['question_text'])}</p>
            <ul class="mb-0 ps-3">{"".join(_answer_summary_row(a) for a in question["answers"])}</ul>
        </li>
        """
        for index, question in enumerate(quiz["questions"])
    ) or '<li class="list-group-item text-secondary">No questions yet.</li>'

    return f"""
    <div class="row g-4">
        <div class="col-lg-6">
            <section class="card border-0 shadow-sm mb-4">
                <div class="card-body p-4">
                    <h2 class="h5 mb-3">Quiz details</h2>
                    <form hx-post="{BACKEND_BASE}/quizzes/update" hx-target="#form-result">
                        <input type="hidden" name="quiz_id" value="{quiz_id}">
                        {_quiz_fields(quiz)}
                        <div class="d-flex gap-2">
                            <button class="btn btn-primary" type="submit">Save changes</button>
                            <a class="btn btn-outline-secondary" href="/quiz.html?id={quiz_id}">Cancel</a>
                        </div>
                        <div id="form-result" aria-live="polite"></div>
                    </form>
                </div>
            </section>
        </div>
        <div class="col-lg-6">
            <section class="card border-0 shadow-sm mb-4">
                <div class="card-body p-4">
                    <h2 class="h5 mb-3">Questions</h2>
                    <ul class="list-group list-group-flush mb-0">{questions_html}</ul>
                </div>
            </section>
            <section class="card border-0 shadow-sm">
                <div class="card-body p-4">
                    <h2 class="h5 mb-3">Add a question</h2>
                    <form hx-post="{BACKEND_BASE}/quizzes/{quiz_id}/questions" hx-target="#question-result">
                        <div class="mb-3">
                            <label class="form-label" for="question_text">Question</label>
                            <textarea class="form-control" id="question_text" name="question_text" rows="2" maxlength="500" required></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label" for="explanation">Explanation (shown if answered incorrectly)</label>
                            <textarea class="form-control" id="explanation" name="explanation" rows="2" maxlength="500" required></textarea>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-md-6">
                                <label class="form-label">Option A</label>
                                <input class="form-control" name="answer_1" maxlength="200" required>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Option B</label>
                                <input class="form-control" name="answer_2" maxlength="200" required>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Option C</label>
                                <input class="form-control" name="answer_3" maxlength="200">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Option D</label>
                                <input class="form-control" name="answer_4" maxlength="200">
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label" for="correct_index">Correct option</label>
                            <select class="form-select" id="correct_index" name="correct_index">
                                <option value="0">A</option>
                                <option value="1">B</option>
                                <option value="2">C</option>
                                <option value="3">D</option>
                            </select>
                        </div>
                        <button class="btn btn-primary" type="submit">Add question</button>
                        <div id="question-result" aria-live="polite"></div>
                    </form>
                </div>
            </section>
        </div>
    </div>
    """
