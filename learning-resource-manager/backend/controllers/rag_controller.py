from flask import Blueprint, jsonify, request

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

# Only the query and k are passed on; which service is searched is fixed in
# rag_service. The RAG server checks both and answers a 400 saying what is wrong.
@rag_bp.route('/retrieve', methods=['POST'])
def retrieve():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}

    return _relay(lambda: rag_service.retrieve(payload.get("query"), payload.get("k")))

# Takes no body: which service is indexed is fixed in rag_service, not chosen
# by the page.
@rag_bp.route('/ingest', methods=['POST'])
def ingest():
    return _relay(rag_service.ingest)
