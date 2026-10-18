import jwt
from flask import Blueprint, current_app, jsonify, request


auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/auth/verify")
def verify_token():
    secret = current_app.config["JWT_SECRET"]
    if len(secret.encode("utf-8")) < 32:
        return jsonify(error="Token verification is not configured."), 503

    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return jsonify(error="A Bearer token is required."), 401
    try:
        claims = jwt.decode(
            token.strip(), secret, algorithms=["HS256"], options={"require": ["sub", "exp"]}
        )
        if not isinstance(claims["sub"], str) or not claims["sub"].strip():
            raise jwt.InvalidTokenError("Invalid subject")
    except jwt.PyJWTError:
        return jsonify(error="The token is invalid or expired."), 401
    return jsonify(sub=claims["sub"]), 200
