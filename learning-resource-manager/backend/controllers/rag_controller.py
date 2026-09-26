from flask import Blueprint, jsonify

from services import rag_service
from services.rag_service import RagError

rag_bp = Blueprint('rag', __name__)

def _relay(call):
    """Hand the RAG server's response to the page as it came, or a 503 when
    there was no response to hand on."""
    try:
        status, body = call()
    except RagError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503

    return jsonify(body), status

@rag_bp.route('/health', methods=['GET'])
def health():
    return _relay(rag_service.health)

# Takes no body: which service is indexed is fixed in rag_service, not chosen
# by the page.
@rag_bp.route('/ingest', methods=['POST'])
def ingest():
    return _relay(rag_service.ingest)
