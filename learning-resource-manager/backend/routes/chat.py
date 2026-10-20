from flask import Blueprint, jsonify, request

from services.chat_service import ChatError, send_message

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/send_message', methods=['POST'])
def send():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or request.form.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Ask a question to search the library."}), 400

    try:
        return jsonify({"reply": send_message(message)})
    except ChatError as exc:
        return jsonify({"error": str(exc)}), 503
