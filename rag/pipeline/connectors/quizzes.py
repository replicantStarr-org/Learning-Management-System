from ..common import Connector, Record, pick

connector = Connector("quizzes", "http://localhost:6004")


@connector.entity
def quizzes(get):
    # The list omits questions; the detail includes them with their answers.
    # Each question is its own record so a search returns just the question
    # that matches, not a chunk of several where the model may read the wrong one.
    for row in get("/quizzes"):
        quiz = get(f"/quizzes/{row['quiz_id']}")
        yield Record(
            entity="quiz",
            id=quiz["quiz_id"],
            title=quiz["title"],
            fields={
                **pick(quiz, "subject_name", "title", "difficulty", "description"),
                "questions": [q["question_text"] for q in quiz["questions"]],
            },
        )
        for number, question in enumerate(quiz["questions"], start=1):
            answers = question["answers"]
            yield Record(
                entity="quiz_question",
                id=question["question_id"],
                title=f"{quiz['title']}, question {number}",
                fields={
                    "quiz": quiz["title"],
                    "subject_name": quiz["subject_name"],
                    "question": question["question_text"],
                    "correct_answer": [a["answer_text"] for a in answers if a["is_correct"]],
                    "other_options": [a["answer_text"] for a in answers if not a["is_correct"]],
                    "explanation": question["explanation"],
                },
            )
