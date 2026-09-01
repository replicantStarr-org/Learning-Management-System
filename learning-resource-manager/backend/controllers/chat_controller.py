from flask import Blueprint
import os

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/send_message')
def send_message():
    return "No Message"
