from .learning_resources import collect_evidence as collect_resource_evidence
from .subjects import collect_evidence as collect_subject_evidence

CONNECTORS = {
    'subjects': collect_subject_evidence,
    'resources': collect_resource_evidence,
}
