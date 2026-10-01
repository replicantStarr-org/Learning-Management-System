from flask import Flask
from flask_cors import CORS

from routes.mcp import mcp_bp
from routes.quizzes import quizzes_bp
from routes.rag import rag_bp


def create_app():
    app = Flask(__name__)
    CORS(app, expose_headers=["HX-Error", "HX-Redirect", "HX-Trigger"])
    app.register_blueprint(quizzes_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(mcp_bp)

    @app.get("/")
    def health():
        return "Quiz backend is running."

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
