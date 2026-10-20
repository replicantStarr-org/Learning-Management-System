import time

import jwt
from flask import Blueprint, current_app, jsonify, request

auth_bp = Blueprint("auth_mode", __name__)

TOKEN_LIFETIME_SECONDS = 300  # 5 minute expiry
# Below this PyJWT warns that HS256 keys are insecure.
MIN_SECRET_BYTES = 32


def _secret():
    """The signing secret from app config (see services/token_secret.py), or
    None when it is too short to sign or verify with."""
    secret = current_app.config.get("JWT_SECRET", "")
    return secret if len(secret.encode("utf-8")) >= MIN_SECRET_BYTES else None


def _not_configured():
    return jsonify({"error": "Token signing is not configured."}), 503


@auth_bp.post("/auth/token")
def issue_token():
    secret = _secret()
    if secret is None:
        return _not_configured()
    token = jwt.encode(
        {"sub": "test-user", "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS},
        secret,
        algorithm="HS256",
    )
    return jsonify({"token": token}), 200


@auth_bp.get("/auth/verify")
def verify_token():
    # Checked like the subjects service's /auth/verify (subjects/backend/routes/auth.py).
    secret = _secret()
    if secret is None:
        return _not_configured()

    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return jsonify({"error": "A Bearer token is required."}), 401
    try:
        claims = jwt.decode(
            token.strip(), secret, algorithms=["HS256"], options={"require": ["sub", "exp"]}
        )
        if not isinstance(claims["sub"], str) or not claims["sub"].strip():
            raise jwt.InvalidTokenError("Invalid subject")
    except jwt.PyJWTError:
        # Expired, badly signed and malformed tokens are not told apart.
        return jsonify({"error": "The token is invalid or expired."}), 401
    return jsonify({"sub": claims["sub"]}), 200
