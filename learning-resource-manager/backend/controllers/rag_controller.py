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

def _query_and_k():
    """The only two values the page may send when searching.

    Which service is searched is fixed in rag_service. Neither value is checked
    here: the RAG server does that and answers a 400 saying what is wrong.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}

    return payload.get("query"), payload.get("k")

@rag_bp.route('/retrieve', methods=['POST'])
def retrieve():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.retrieve(query, k))

@rag_bp.route('/answer', methods=['POST'])
def answer():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.answer(query, k))

# Takes no body: which service is indexed is fixed in rag_service, not chosen
# by the page.
@rag_bp.route('/ingest', methods=['POST'])
def ingest():
    return _relay(rag_service.ingest)

# Takes no body, like ingest, so the page can only ever clear this service.
@rag_bp.route('/clear', methods=['POST'])
def clear():
    return _relay(rag_service.clear)
