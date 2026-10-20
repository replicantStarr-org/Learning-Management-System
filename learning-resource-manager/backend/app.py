from flask import Flask

from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.highlights import highlights_bp
from routes.mcp import mcp_bp
from routes.multi_agent import multi_agent_bp
from routes.rag import rag_bp
from routes.resources import resources_bp
from services.deployment import configure_deployment
from services.token_secret import load_jwt_secret


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    # Matches client_max_body_size in the frontend nginx config.
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    app.config["JWT_SECRET"] = load_jwt_secret(app.instance_path)
    configure_deployment(app, {"chat.send"})
    register_blueprints(app)
    return app

def register_blueprints(app):
    app.register_blueprint(resources_bp, url_prefix='/api/resources')
    app.register_blueprint(highlights_bp, url_prefix='/api/highlights')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(rag_bp, url_prefix='/api/rag')
    app.register_blueprint(mcp_bp, url_prefix='/api/mcp')
    app.register_blueprint(multi_agent_bp, url_prefix='/api/multi-agent')
    # /api/auth/token and /api/auth/verify, under /api so the frontend's
    # nginx proxy reaches them like every other route.
    app.register_blueprint(auth_bp, url_prefix='/api')

app = create_app()

def main():
   app.run(host='0.0.0.0', port=5002, threaded=True)  # noqa: S104 - container ingress

if __name__ == "__main__":
    main()
