from .quizzes import collect_evidence as collect_quiz_evidence
from .resources import collect_evidence as collect_resource_evidence
from .subjects import collect_evidence as collect_subject_evidence

CONNECTORS = {
    'subjects': collect_subject_evidence,
    'quizzes': collect_quiz_evidence,
    'resources': collect_resource_evidence,
}
