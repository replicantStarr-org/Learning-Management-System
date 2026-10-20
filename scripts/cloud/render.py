"""Render private Azure Container App (ACA) manifests.

Every container app contains an entire feature.
A purpose built 'edge' docker container handles ingress traffic, forwarding to the real frontend container.
The edge enforces the HTTP authentication for each frontend as an independent component.

These are private manifests that must not be tracked in source, e.g. configuration.secrets contains credentials.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def render(state: Path, profile: str):
    if profile not in {"default", "bonus"}:
        raise ValueError("Unknown deployment profile")

    # load the inventory of services to be deployed
    # each service has the frontend port specified in the config
    inventory = json.loads((ROOT / "cloud/services.json").read_text())

    # load all configuration / information files from the state directory
    images = json.loads((state / "images.json").read_text())
    release = json.loads((state / "release.json").read_text())
    environment = json.loads((state / "environment.json").read_text())
    identity = (state / "runtime-identity").read_text().strip()
    auth = json.loads((state / "auth.json").read_text())
    # models.json is created by model.sh which is only run for the bonus profile
    models = json.loads((state / "models.json").read_text()) if profile == "bonus" else {}

    # create the output directory for the rendered manifests
    out = state / "manifests"
    out.mkdir(exist_ok=True)

    for feature in inventory:
        name, port = feature["name"], feature["port"]

        # used to map to database and backend ports
        index = port - 3000  # ports generally follow a pattern, 3000, 3001, 3002, ...

        ai_services_enabled = profile == "bonus"
        flags = {key: str(ai_services_enabled).lower() for key in (
            "AI_MODE_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED")}

        secrets = [
            {"name": "edge-auth", "value": auth["htpasswd"]},
            {"name": "jwt-secret", "value": auth["jwt"]}
        ]

        backend_env = {
            **flags,
            "DATABASE_SERVICE_URL": f"http://127.0.0.1:{6000 + index}",
            "FRONTEND_URL": f"https://lh-{name}.{environment['domain']}",
            "CLOUD_DEPLOYMENT": "true",
            "DEPLOYMENT_PROFILE": profile,
            # frontend URLs for all services in the inventory
            **{f"{f['name'].upper()}_FRONTEND_URL": f"https://lh-{f['name']}.{environment['domain']}" for f in inventory},
            # add shared JWT secret that can be used for any service
            # that wants to validate JWT tokens
            "JWT_SECRET": "secret:jwt-secret"  # noqa: S105 - secret reference, not a credential
        }

        if name in {"assignments", "quizzes"}:
            backend_env["SUBJECTS_PUBLIC_SERVICE_URL"] = f"https://lh-subjects.{environment['domain']}/public"

        if name == "access":
            backend_env["COOKIE_DOMAIN"] = environment["domain"]

        if ai_services_enabled:
            backend_env.update({
                "MCP_SERVER_URL": "http://127.0.0.1:8000/mcp",
                "RAG_SERVER_URL": "http://127.0.0.1:5010",
                "MULTI_AGENT_SERVICE_URL": "http://127.0.0.1:15004",
            })


        # build a dictionary representing a container configuration
        def container(key, image, env=None, command=None, cpu=0.25, memory="0.5Gi", probe_port=None):
            result = {
                "name": key,
                "image": images[image],
                "resources": {"cpu": cpu, "memory": memory},
                # env with name and either a value or a secretRef (denoted by value prefix "secret:")
                "env": [{"name": k,
                          **({"secretRef": v[7:]} if v.startswith("secret:") else {"value": v})}
                        for k, v in (env or {}).items()]
            }

            if command:
                result["command"] = command

            if probe_port:
                result["probes"] = [{"type": kind, "tcpSocket": {"port": probe_port}, "periodSeconds": 10,
                                     "initialDelaySeconds": 5, "failureThreshold": 30 if kind == "Startup" else 3}
                                    for kind in ("Startup", "Readiness", "Liveness")]

            return result

        inference_env = {}
        if ai_services_enabled:
            secrets.append({"name": "inference-key", "value": models["key"]})
            inference_env = {"OPENAI_BASE_URL": models["endpoint"], "OPENAI_API_KEY": "secret:inference-key",
                         "OPENAI_MODEL": "primary", "OPENAI_REVIEW_MODEL": "reviewer"}
            backend_env.update(inference_env)

        # standard set of containers for all deployments
        containers = [
            container("edge", "edge", {"FRONTEND_PORT": str(port), "AUTH_HTPASSWD": "secret:edge-auth"}, probe_port=8080),
            container("frontend", f"{name}-frontend", probe_port=port),
            container("backend", f"{name}-backend", backend_env, probe_port=5000 + index),
            container("database", f"{name}-database",
                      {"DATABASE_PATH": "/app/data", "DATABASE_NAME": "resources.db"} if name == "resources" else {},
                      probe_port=6000 + index),
        ]

        volumes = []
        if name == "resources":
            # Seed the shared EmptyDir before nginx starts. Seeds live outside
            # /content in the frontend image so the mount cannot hide them.
            containers[1]["env"].append({"name": "SEED_CONTENT", "value": "true"})
            # Both uploads and seeded PDFs are served directly by nginx.
            volumes.append({"name": "content", "storageType": "EmptyDir"})
            for c in containers:
                if c["name"] in {"frontend", "backend"}:
                    # mount the shared content volume to the frontend and backend containers
                    c["volumeMounts"] = [{"volumeName": "content", "mountPath": "/content"}]

            # override the command for the database container to make the /app/data directory
            # the resources container creates the database at launch vs other services that do it at build time
            containers[3]["command"] = ["sh", "-c", "mkdir -p /app/data && python database_init.py && exec gunicorn --bind 0.0.0.0:6002 --workers 1 --threads 4 app:app"]

        # add AI services containers if enabled
        if ai_services_enabled:
            containers.extend([
                container("mcp", "mcp", command=["python", "server.py"], probe_port=8000),
                container("rag", "rag-server", {**inference_env, "RAG_ENABLED": "true"},
                          ["python", "-m", "server.http_server"], cpu=0.5, memory="1Gi", probe_port=5010),
                container("multi-agent", "multi-agent-server", {**inference_env, "HOST": "0.0.0.0", "PORT": "15004"},  # noqa: S104 - container namespace, no service ingress
                          ["python", "app.py"], probe_port=15004),
            ])

        # create final manifst based on containers, secrets and volumes
        registry_server = images["edge"].split("/")[0]
        manifest = {
            "name": f"lh-{name}",
            "type": "Microsoft.App/containerApps",
            "location": os.environ.get("LOCATION", "australiaeast"),
            "identity": {"type": "UserAssigned", "userAssignedIdentities": {identity: {}}},
            "tags": {"profile": profile, "release": release["release"],
                     "activeUntil": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "properties": {
                "environmentId": environment["id"],
                "workloadProfileName": "Consumption",
                "configuration": {"activeRevisionsMode": "Single", "secrets": secrets,
                    "registries": [{"server": registry_server, "identity": identity}],
                    "ingress": {"external": True, "targetPort": 8080, "transport": "http", "allowInsecure": False}},
                "template": {"containers": containers, "volumes": volumes,
                    # TODO: minReplicas = 1 before submission so the service is always instantly available
                    # set to 0 during development to save costs
                    "scale": {"minReplicas": 0, "maxReplicas": 1, "cooldownPeriod": 300,
                              "rules": [{"name": "http", "http": {"metadata": {"concurrentRequests": "10"}}}]}},
            },
        }
        (out / f"{name}.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
        # read and writeable by the owner only (contains sensitive information such as secrets)
        (out / f"{name}.yaml").chmod(0o600)


if __name__ == "__main__":
    render(Path(os.environ.get("STATE_DIR", ROOT / ".cloud")), os.environ.get("PROFILE", "default"))
