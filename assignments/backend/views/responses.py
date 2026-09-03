from flask import jsonify, make_response, request


BACKEND_BASE = "http://localhost:5003"
FRONTEND_BASE = "http://localhost:3003"


def wants_html():
    """HTMX asks for hypermedia; anything else (curl, CI, other services) gets JSON.

    This is what lets one route satisfy both the REST API required by the specification and
    the HTML-over-the-wire frontend, without duplicating the route table.
    """
    return request.headers.get("HX-Request", "").lower() == "true"


def respond(payload, render, status=200, trigger=None, redirect=None):
    response = make_response(render(payload) if wants_html() else jsonify(payload), status)
    if trigger:
        response.headers["HX-Trigger"] = trigger
    if redirect:
        response.headers["HX-Redirect"] = redirect
    return response


def respond_error(message, status, render, details=None):
    """Errors follow the same split: a real status code for API clients, and a 200 carrying an
    alert fragment for HTMX, which does not swap non-2xx responses by default."""
    if wants_html():
        response = make_response(render(message), 200)
        response.headers["HX-Error"] = "true"
        return response

    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status
