from flask import Flask
from flask_cors import CORS

from routes.ai import ai_bp
from routes.assignments import assignments_bp
from routes.reminders import reminders_bp
from services.errors import ServiceError, UpstreamError
from views.html import error
from views.responses import respond_error


def create_app():
    app = Flask(__name__)
    CORS(app, expose_headers=["HX-Error", "HX-Redirect", "HX-Trigger"])

    app.register_blueprint(assignments_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(reminders_bp)

    @app.errorhandler(ServiceError)
    def handle_service_error(exc):
        return respond_error(str(exc), exc.status, error, exc.details)

    @app.errorhandler(UpstreamError)
    def handle_upstream_error(exc):
        return respond_error(str(exc), exc.status, error)

    @app.get("/")
    def health():
        return "Assignment backend is running."

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
