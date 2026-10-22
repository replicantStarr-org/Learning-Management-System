from .assignments import collect_evidence as collect_assignment_evidence
from .quizzes import collect_evidence as collect_quiz_evidence
from .resources import collect_evidence as collect_resource_evidence
from .subjects import collect_evidence as collect_subject_evidence
from .timetable import collect_evidence as collect_timetable_evidence

CONNECTORS = {
    'assignments': collect_assignment_evidence,
    'subjects': collect_subject_evidence,
    'quizzes': collect_quiz_evidence,
    'resources': collect_resource_evidence,
    'timetable': collect_timetable_evidence,
}
