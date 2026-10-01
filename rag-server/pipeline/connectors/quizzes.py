from ..connector import Connector, Record

connector = Connector("quizzes", "http://localhost:6004")

# Indexed: quizzes, each of their questions, and attempt results. Left out:
# quizzes whose source is "ai_generated" (the model wrote every question, so it
# would cite its own output back as evidence) and attempts' ai_feedback.
AI_SOURCE = "ai_generated"


def _authored_quizzes(get):
    # List, then detail: /quizzes omits the questions and their answers.
    for row in get("/quizzes"):
        if row["source"] != AI_SOURCE:
            yield get(f"/quizzes/{row['quiz_id']}")


@connector.entity
def quizzes(get):
    for quiz in _authored_quizzes(get):
        yield Record(
            entity="quiz",
            id=quiz["quiz_id"],
            title=f"{quiz['title']} ({quiz['subject_name']})",
            fields={
                "quiz": quiz["title"],
                "subject": quiz["subject_name"],
                "difficulty": quiz["difficulty"],
                "description": quiz["description"],
                "number of questions": len(quiz["questions"]),
                "questions": [question["question_text"] for question in quiz["questions"]],
            },
        )


@connector.entity
def questions(get):
    # Each question is its own record, repeating its quiz and subject, so a
    # question about one answer is not answered from a neighbouring question.
    for quiz in _authored_quizzes(get):
        for number, question in enumerate(quiz["questions"], start=1):
            answers = question["answers"]
            yield Record(
                entity="quiz_question",
                id=question["question_id"],
                title=f"{quiz['title']}, question {number}",
                fields={
                    "quiz": quiz["title"],
                    "subject": quiz["subject_name"],
                    "question": question["question_text"],
                    "answer options": [answer["answer_text"] for answer in answers],
                    "correct answer": next(
                        (answer["answer_text"] for answer in answers if answer["is_correct"]), None
                    ),
                    "explanation": question["explanation"],
                },
            )


@connector.entity
def attempts(get):
    # Fan-out: attempts are only served per quiz.
    for quiz in _authored_quizzes(get):
        for attempt in get(f"/quizzes/{quiz['quiz_id']}/attempts"):
            score, total = attempt["score"], attempt["total_questions"]
            percent = round(100 * score / total) if total else 0
            completed = attempt["completed_at"]
            yield Record(
                entity="quiz_attempt",
                id=attempt["attempt_id"],
                title=f"{attempt['student_name']} - {quiz['title']} attempt",
                fields={
                    "student": attempt["student_name"],
                    "quiz": quiz["title"],
                    "subject": quiz["subject_name"],
                    "score": f"{score} out of {total} ({percent}%)",
                    "full marks": "yes" if total and score == total else "no",
                    # The date only; the time of day is never asked about.
                    "completed on": completed[:10] if completed else "not completed",
                },
            )
