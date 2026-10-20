"""The secret tokens are signed with. Copied from the subjects service
(subjects/backend/services/token_secret.py): JWT_SECRET when configured, which
cloud always does, otherwise one generated per checkout so no secret lives in
source. It is written once to the instance folder, so every gunicorn worker
signs and verifies with the same one."""
import os
import secrets
import tempfile
from pathlib import Path


def load_jwt_secret(instance_path):
    configured = os.getenv("JWT_SECRET")
    if configured:
        return configured

    path = Path(instance_path) / "jwt-secret"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as pending:
            temporary = Path(pending.name)
            pending.write(secrets.token_urlsafe(64))
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink()

    generated = path.read_text(encoding="utf-8").strip()
    if len(generated.encode("utf-8")) < 32:
        raise ValueError(
            "The stored JWT secret is invalid; "
            "configure JWT_SECRET or remove the invalid local file"
        )
    return generated
