import os
import re
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from flask_cors import CORS

from routes.api import api_bp
from routes.auth import auth_bp
from routes.mcp import mcp_bp
from routes.rag import rag_bp
from routes.multi_agent import multi_agent_bp
from routes.subjects import subjects_bp
from services.token_secret import load_jwt_secret


def create_app():
    app = Flask(__name__)
    app.config["JWT_SECRET"] = load_jwt_secret(app.instance_path)
    cloud = os.getenv("CLOUD_DEPLOYMENT", "false").lower() == "true"
    if not cloud:
        CORS(app, expose_headers=["HX-Error", "HX-Redirect", "HX-Trigger"])

    @app.before_request
    def runtime_controls():
        if cloud and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
                origin and (urlsplit(origin).scheme != "https" or urlsplit(origin).netloc != request.host)
            ):
                return jsonify(error="Cross-origin mutations are not allowed."), 403
        ai_request = request.path == "/subjects/questions" or re.fullmatch(r"/subjects/\d+/summary", request.path)
        if ai_request and os.getenv("AI_MODE_ENABLED", "true").lower() not in {"true", "1", "yes", "on"}:
            response = jsonify(error="AI mode is disabled in this deployment.", enabled=False)
            response.headers["HX-Error"] = "true"
            return response, 403

    @app.get("/config")
    def runtime_config():
        flags = {name: os.getenv(name, "true").lower() in {"true", "1", "yes", "on"}
                 for name in ("AI_MODE_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED")}
        return jsonify(profile=os.getenv("DEPLOYMENT_PROFILE", "local"), flags=flags,
                       navigation={name: os.getenv(f"{name.upper()}_FRONTEND_URL", f"http://localhost:{port}")
                                   for name, port in (("access", 3000), ("resources", 3002),
                                                      ("assignments", 3003), ("quizzes", 3004), ("timetable", 3005))})
    app.register_blueprint(subjects_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(multi_agent_bp)

    @app.get("/")
    def health():
        return "Subject backend is running."

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)  # noqa: S104 - container ingress
