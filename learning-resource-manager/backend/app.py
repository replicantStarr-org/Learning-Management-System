from flask import Flask

from controllers.auth_controller import auth_bp
from controllers.chat_controller import chat_bp
from controllers.highlights_controller import highlights_bp
from controllers.mcp_controller import mcp_bp
from controllers.multi_agent_controller import multi_agent_bp
from controllers.rag_controller import rag_bp
from controllers.resources_controller import resources_bp
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
