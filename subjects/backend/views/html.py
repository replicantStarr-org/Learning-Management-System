from html import escape


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<p role="status">{escaped(text)}</p>'


def error(text):
    return f'<p role="alert">{escaped(text)}</p>'


def subject_list(subjects):
    if not subjects:
        return "<p>No subjects have been created.</p>"
    items = "".join(
        f"<li>{escaped(subject['subject_id'])}: {escaped(subject['code'])} - "
        f"{escaped(subject['name'])}</li>"
        for subject in subjects
    )
    return f"<ul>{items}</ul>"


def subject_detail(subject):
    return (
        f"<p><strong>{escaped(subject['code'])}: {escaped(subject['name'])}</strong><br>"
        f"Semester: {escaped(subject['semester'])}<br>"
        f"Coordinator: {escaped(subject['coordinator'])}<br>"
        f"Status: {escaped(subject['status'])}<br>"
        f"Description: {escaped(subject['description'])}</p>"
    )


def summary_result(summary):
    source = "Saved summary" if summary.get("reused") else "New summary"
    return f"<p><strong>{source}</strong><br>{escaped(summary['ai_response'])}</p>"


def question_result(result):
    return f"<p><strong>Answer</strong><br>{escaped(result['answer'])}</p>"
