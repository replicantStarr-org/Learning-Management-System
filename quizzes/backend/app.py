from flask import Flask
from flask_cors import CORS

from routes.ai_mode import ai_mode_bp
from routes.mcp import mcp_bp
from routes.quizzes import quizzes_bp
from routes.rag import rag_bp
from services.deployment import configure_deployment, enabled


def create_app():
    app = Flask(__name__)
    if not enabled("CLOUD_DEPLOYMENT", "false"):
        CORS(app, expose_headers=["HX-Error", "HX-Redirect", "HX-Trigger"])
    configure_deployment(app, {
        "quizzes.attempt_feedback", "quizzes.create_quiz_generation",
        "quizzes.create_subject_quiz_generation",
    })
    app.register_blueprint(quizzes_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(ai_mode_bp)

    @app.get("/")
    def health():
        return "Quiz backend is running."

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)  # noqa: S104 - container ingress
