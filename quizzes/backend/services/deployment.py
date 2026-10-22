"""Public runtime configuration and same-origin cloud request controls."""
import os
from urllib.parse import urlsplit

from flask import jsonify, request


def enabled(name, default="true"):
    return os.getenv(name, default).strip().lower() in {"true", "1", "yes", "on"}


def configure_deployment(app, ai_routes=()):
    cloud = enabled("CLOUD_DEPLOYMENT", "false")

    @app.before_request
    def runtime_controls():
        if cloud and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
                origin and (
                    urlsplit(origin).scheme != "https" or urlsplit(origin).netloc != request.host
                )
            ):
                return jsonify(error="Cross-origin mutations are not allowed."), 403
        ai_enabled = enabled("AI_MODE_ENABLED", "false" if cloud else "true")
        if request.endpoint in ai_routes and not ai_enabled:
            message = "AI mode is disabled in this deployment. You can still use the manual tools."
            if request.headers.get("HX-Request", "").lower() == "true":
                body = f'<div class="alert alert-secondary" role="status">{message}</div>'
                return body, 200, {"HX-Error": "true"}
            return jsonify(error=message), 403

    @app.get("/config")
    def runtime_config():
        flags = {name: enabled(name) for name in ("MCP_ENABLED", "RAG_ENABLED")}
        # Same cloud-aware default as the multi-agent route guard.
        flags["MULTI_AGENT_ENABLED"] = enabled("MULTI_AGENT_ENABLED", "false" if cloud else "true")
        flags["AI_MODE_ENABLED"] = enabled("AI_MODE_ENABLED", "false" if cloud else "true")
        names = ("access", "subjects", "resources", "assignments", "quizzes", "timetable")
        return jsonify(
            profile=os.getenv("DEPLOYMENT_PROFILE", "local"), flags=flags,
            navigation={
                name: os.getenv(f"{name.upper()}_FRONTEND_URL", f"http://localhost:{3000 + index}")
                for index, name in enumerate(names)
            },
        )
