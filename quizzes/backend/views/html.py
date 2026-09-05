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
                    hx-delete="{BACKEND_BASE}/quizzes/{quiz_id}"
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


OPTION_LETTERS = ("A", "B", "C", "D")


def _answer_display_chip(answer):
    if answer["is_correct"]:
        return f"""
        <div class="col">
            <div class="answer-chip d-flex align-items-center gap-2 px-3 py-2 rounded border border-success-subtle bg-success-subtle text-success-emphasis">
                <i class="bi bi-check-circle-fill flex-shrink-0" aria-hidden="true"></i>
                <span>{escaped(answer['answer_text'])}</span>
            </div>
        </div>
        """
    return f"""
    <div class="col">
        <div class="answer-chip d-flex align-items-center gap-2 px-3 py-2 rounded border bg-body">
            <i class="bi bi-circle text-secondary flex-shrink-0" aria-hidden="true"></i>
            <span>{escaped(answer['answer_text'])}</span>
        </div>
    </div>
    """


def _question_action_buttons(quiz_id, question_id):
    return f"""
    <div class="d-flex gap-1 flex-shrink-0">
        <button class="btn btn-sm btn-outline-secondary" type="button" title="Edit question"
                hx-get="{BACKEND_BASE}/quizzes/{quiz_id}/questions/{question_id}?view=edit"
                hx-target="#question-{question_id}" hx-swap="outerHTML">
            <i class="bi bi-pencil" aria-hidden="true"></i>
        </button>
        <button class="btn btn-sm btn-outline-danger" type="button" title="Delete question"
                hx-delete="{BACKEND_BASE}/quizzes/{quiz_id}/questions/{question_id}"
                hx-target="#question-{question_id}" hx-swap="outerHTML"
                hx-confirm="Delete this question permanently?">
            <i class="bi bi-trash" aria-hidden="true"></i>
        </button>
    </div>
    """


def question_display(quiz_id, question, index=None):
    question_id = question["question_id"]
    number = f"Q{index + 1}" if index is not None else "Q"
    answers_html = "".join(_answer_display_chip(a) for a in question["answers"])
    return f"""
    <div class="card question-card mb-3" id="question-{question_id}">
        <div class="card-body p-4">
            <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
                <div class="d-flex align-items-start gap-2">
                    <span class="badge text-bg-primary mt-1">{number}</span>
                    <p class="fw-semibold mb-0">{escaped(question['question_text'])}</p>
                </div>
                {_question_action_buttons(quiz_id, question_id)}
            </div>
            <div class="row row-cols-1 row-cols-md-2 g-2">{answers_html}</div>
        </div>
    </div>
    """


def _answer_option_rows(values, required_count=2):
    def row(i, letter):
        value = escaped(values[i]) if i < len(values) else ""
        placeholder = "Answer option" if i < required_count else "Answer option (optional)"
        required = "required" if i < required_count else ""
        return f"""
        <div class="d-flex align-items-center gap-2 mb-2">
            <span class="badge bg-light text-dark border fw-normal" style="min-width:1.75rem;">{letter}</span>
            <input class="form-control" name="answer_{i + 1}" maxlength="200"
                   placeholder="{placeholder}" value="{value}" {required}>
        </div>
        """

    return "".join(row(i, letter) for i, letter in enumerate(OPTION_LETTERS))


def _correct_index_select(field_id, values, correct_index, show_all=False):
    def label(i, letter):
        text = values[i] if i < len(values) else ""
        return f"{letter} - {text}" if text else letter

    indices = range(4) if show_all else [
        i for i in range(4) if i < 2 or (i < len(values) and values[i])
    ]
    options = "".join(
        f'<option value="{i}"{" selected" if i == correct_index else ""}>{escaped(label(i, OPTION_LETTERS[i]))}</option>'
        for i in indices
    )
    return f'<select class="form-select" id="{field_id}" name="correct_index">{options}</select>'


def question_edit_form(quiz_id, question):
    question_id = question["question_id"]
    answers = question["answers"]
    values = [a["answer_text"] for a in answers]
    correct_index = next((i for i, a in enumerate(answers) if a["is_correct"]), 0)

    return f"""
    <div class="card question-card question-edit-card mb-3" id="question-{question_id}">
        <div class="card-body p-4">
            <form hx-put="{BACKEND_BASE}/quizzes/{quiz_id}/questions/{question_id}"
                  hx-target="#question-{question_id}" hx-swap="outerHTML">
                <div class="mb-3">
                    <label class="form-label small text-secondary text-uppercase fw-semibold">Question</label>
                    <textarea class="form-control form-control-lg" name="question_text" rows="2"
                              maxlength="500" required>{escaped(question['question_text'])}</textarea>
                </div>
                <div class="mb-3">
                    <label class="form-label small text-secondary text-uppercase fw-semibold">Answer options</label>
                    {_answer_option_rows(values)}
                </div>
                <div class="mb-3 col-md-6">
                    <label class="form-label small text-secondary text-uppercase fw-semibold" for="correct_index-{question_id}">Correct answer</label>
                    {_correct_index_select(f"correct_index-{question_id}", values, correct_index)}
                </div>
                <div class="mb-3">
                    <label class="form-label small text-secondary text-uppercase fw-semibold">Explanation
                        <span class="text-secondary fw-normal text-lowercase">(shown if answered incorrectly)</span>
                    </label>
                    <textarea class="form-control" name="explanation" rows="2"
                              maxlength="500" required>{escaped(question['explanation'])}</textarea>
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-primary" type="submit"><i class="bi bi-check-lg me-1" aria-hidden="true"></i>Save</button>
                    <button class="btn btn-outline-secondary" type="button"
                            hx-get="{BACKEND_BASE}/quizzes/{quiz_id}/questions/{question_id}"
                            hx-target="#question-{question_id}" hx-swap="outerHTML">Cancel</button>
                </div>
            </form>
        </div>
    </div>
    """


def questions_panel(quiz_id, questions):
    if not questions:
        return """
        <div class="text-center py-5 text-secondary border rounded-3 bg-body-tertiary">
            <i class="bi bi-inbox display-6 d-block mb-2" aria-hidden="true"></i>
            No questions yet - add one below.
        </div>
        """
    return "".join(
        question_display(quiz_id, question, index=index)
        for index, question in enumerate(questions)
    )


def quiz_edit_form(quiz):
    quiz_id = escaped(quiz["quiz_id"])
    add_correct_select = _correct_index_select("correct_index", [], 0, show_all=True)
    return f"""
    <section class="card border-0 shadow-sm mb-4 bg-body-tertiary">
        <div class="card-body p-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="h6 text-secondary text-uppercase fw-semibold mb-0">
                    <i class="bi bi-gear me-1" aria-hidden="true"></i>Quiz details
                </h2>
                <a class="btn btn-sm btn-outline-secondary" href="/quiz.html?id={quiz_id}">
                    <i class="bi bi-x-lg me-1" aria-hidden="true"></i>Close
                </a>
            </div>
            <form hx-put="{BACKEND_BASE}/quizzes/{quiz_id}" hx-target="#form-result">
                {_quiz_fields(quiz)}
                <div class="d-flex gap-2">
                    <button class="btn btn-primary" type="submit">Save details</button>
                </div>
                <div id="form-result" aria-live="polite"></div>
            </form>
        </div>
    </section>

    <section>
        <div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom border-2">
            <h2 class="h4 mb-0"><i class="bi bi-list-check me-2 text-primary" aria-hidden="true"></i>Questions</h2>
        </div>

        <div id="questions-panel"
             hx-get="{BACKEND_BASE}/quizzes/{quiz_id}/questions"
             hx-trigger="load, questionsChanged from:body"
             hx-swap="innerHTML">
            <div class="text-center py-4" role="status">
                <span class="spinner-border spinner-border-sm text-primary" aria-hidden="true"></span>
            </div>
        </div>

        <div class="card border-0 shadow-sm mt-4">
            <div class="card-body p-4">
                <h3 class="h6 text-uppercase text-secondary fw-semibold mb-3">
                    <i class="bi bi-plus-circle me-1" aria-hidden="true"></i>Add a new question
                </h3>
                <form hx-post="{BACKEND_BASE}/quizzes/{quiz_id}/questions" hx-target="#question-result">
                    <div class="mb-3">
                        <label class="form-label small text-secondary text-uppercase fw-semibold" for="question_text">Question</label>
                        <textarea class="form-control form-control-lg" id="question_text" name="question_text" rows="2" maxlength="500" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label small text-secondary text-uppercase fw-semibold">Answer options</label>
                        {_answer_option_rows([])}
                    </div>
                    <div class="mb-3 col-md-6">
                        <label class="form-label small text-secondary text-uppercase fw-semibold" for="correct_index">Correct answer</label>
                        {add_correct_select}
                    </div>
                    <div class="mb-3">
                        <label class="form-label small text-secondary text-uppercase fw-semibold" for="explanation">Explanation
                            <span class="text-secondary fw-normal text-lowercase">(shown if answered incorrectly)</span>
                        </label>
                        <textarea class="form-control" id="explanation" name="explanation" rows="2" maxlength="500" required></textarea>
                    </div>
                    <button class="btn btn-primary" type="submit"><i class="bi bi-plus-lg me-1" aria-hidden="true"></i>Add question</button>
                    <div id="question-result" aria-live="polite"></div>
                </form>
            </div>
        </div>
    </section>
    """
