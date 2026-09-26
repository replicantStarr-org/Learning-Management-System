from flask import Blueprint, jsonify

from services import rag_service
from services.rag_service import RagError

rag_bp = Blueprint('rag', __name__)

@rag_bp.route('/health', methods=['GET'])
def health():
    try:
        status, body = rag_service.health()
    except RagError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503

    return jsonify(body), status
