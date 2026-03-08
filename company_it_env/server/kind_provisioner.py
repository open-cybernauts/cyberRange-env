"""Local kind-backed provisioner for creating per-episode lab workloads."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from textwrap import indent
from typing import Any, Protocol

from company_it_env.models import (
    AttackerAccess,
    EpisodeStatus,
    ProvisioningRequest,
    ProvisioningResult,
    RemoteServiceEndpoint,
)
from company_it_env.server.controller import RangeProvisioner

HELPDESK_APP = r"""#!/usr/bin/env python3
import json
import os
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

with open("/opt/episode/helpdesk-data.json", "r", encoding="utf-8") as handle:
    DATA = json.load(handle)

TICKETS = DATA["tickets"]

def search(query: str):
    if DATA["search_mode"] == "unsafe_union" and "UNION" in query.upper():
        if DATA["flag_source"] == "database":
            return [{
                "id": 999,
                "title": DATA["flag_value"],
                "description": DATA["source_manifest"],
                "status": "exfiltrated",
            }]
    lowered = query.lower()
    return [ticket for ticket in TICKETS if lowered in ticket["title"].lower()]

def render_page(query: str, rows: list[dict[str, object]]) -> bytes:
    table_rows = "".join(
        "<tr><td>{id}</td><td>{title}</td><td>{description}</td><td>{status}</td></tr>".format(
            id=row["id"],
            title=escape(str(row["title"])),
            description=escape(str(row["description"])),
            status=escape(str(row["status"])),
        )
        for row in rows
    )
    if not table_rows:
        table_rows = "<tr><td colspan='4'>No matching tickets found.</td></tr>"
    html = f\"\"\"<!doctype html>
<html><body style="font-family:sans-serif;background:#111827;color:#e5e7eb;padding:24px">
<h1>Northbridge Support Portal</h1>
<form action="/helpdesk" method="get">
  <input name="query" value="{escape(query)}" />
  <button type="submit">Search</button>
</form>
<p>Internal API endpoint: <code>/helpdesk/api/search</code></p>
<table border="1" cellpadding="8" cellspacing="0">
  <tr><th>ID</th><th>Title</th><th>Description</th><th>Status</th></tr>
  {table_rows}
</table>
</body></html>\"\"\"
    return html.encode("utf-8")

class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _html(self, payload: bytes, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            return self._json({"status": "ok"})
        if parsed.path == "/helpdesk":
            query = parse_qs(parsed.query).get("query", [""])[0]
            return self._html(render_page(query, search(query) if query else []))
        if parsed.path == "/helpdesk/api/search":
            query = parse_qs(parsed.query).get("query", [""])[0]
            return self._json({"query": query, "rows": search(query), "error": None})
        if parsed.path.startswith("/helpdesk/api/tickets/"):
            ticket_id = parsed.path.rsplit("/", 1)[-1]
            for ticket in TICKETS:
                if str(ticket["id"]) == ticket_id:
                    return self._json(ticket)
            return self._json({"detail": "Ticket not found"}, status=404)
        return self._json({"detail": "Not found"}, status=404)

HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
"""

INTERNAL_APP = r"""#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

with open("/opt/episode/internal-data.json", "r", encoding="utf-8") as handle:
    DATA = json.load(handle)

class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _text(self, payload: str, status=200):
        encoded = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/healthz":
            return self._json({"status": "ok"})
        if self.path == "/internal-api/v1/status":
            if DATA["exploit_path"] != "debug_endpoint_exposure":
                return self._json({"detail": "Not found"}, status=404)
            return self._json(DATA["internal_status"])
        if self.path == "/ops/artifacts":
            if DATA["exploit_path"] != "credential_leak_from_manifest":
                return self._json({"detail": "Not found"}, status=404)
            return self._json({"artifacts": sorted(DATA["artifacts"].keys())})
        if self.path.startswith("/ops/artifacts/"):
            if DATA["exploit_path"] != "credential_leak_from_manifest":
                return self._json({"detail": "Not found"}, status=404)
            artifact_path = self.path.split("/ops/artifacts/", 1)[1]
            artifact = DATA["artifacts"].get(artifact_path)
            if artifact is None:
                return self._json({"detail": "Artifact not found"}, status=404)
            return self._text(artifact)
        return self._json({"detail": "Not found"}, status=404)

HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
"""


class CommandRunner(Protocol):
    def run(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessCommandRunner:
    def run(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            check=check,
        )


@dataclass
class KindRangeProvisioner(RangeProvisioner):
    """Provisioner that uses kind and kubectl against a local Docker Desktop cluster."""

    cluster_name: str = "openenv-range"
    namespace_prefix: str = "episode"
    auto_create_cluster: bool = True
    kind_path: str = "kind"
    kubectl_path: str = "kubectl"
    attacker_image: str = "nicolaka/netshoot:latest"
    app_image: str = "python:3.11-slim"
    runner: CommandRunner = field(default_factory=SubprocessCommandRunner)
    remote_url: str | None = None

    def __post_init__(self) -> None:
        self.remote_url = f"kind://{self.cluster_name}"
        self._episodes: dict[str, dict[str, Any]] = {}

    @property
    def kubectl_context(self) -> str:
        return f"kind-{self.cluster_name}"

    def health(self) -> dict[str, Any]:
        cluster_exists = self.cluster_name in self._kind_clusters()
        return {
            "status": "ok" if cluster_exists else "degraded",
            "backend": "kind",
            "cluster_name": self.cluster_name,
            "cluster_exists": cluster_exists,
            "kubectl_context": self.kubectl_context,
        }

    def provision_episode(self, request: ProvisioningRequest) -> ProvisioningResult:
        self._ensure_cluster()
        namespace = request.layout.namespace
        target_services = self._build_cluster_service_endpoints(request)
        self._kubectl_apply(self._build_episode_manifest(request, namespace))
        attacker_access = AttackerAccess(
            connection_type="simulated_shell",
            workspace_label=f"kind-{request.controller_episode_id[:8]}",
            host=self.kubectl_context,
            username="operator",
            bootstrap_commands=[
                f"kubectl --context {self.kubectl_context} exec -it -n {namespace} deploy/redteam -- bash",
                "nmap -Pn -sV " + " ".join(service.host for service in target_services),
            ],
            reachable_hosts=[service.host for service in target_services],
            target_services=target_services,
            constraints=[
                "Enter the redteam pod via kubectl exec before touching target services.",
                "Target services are reachable over the in-cluster network only.",
                "No shared filesystem is mounted from the targets into the redteam pod.",
            ],
        )
        status = EpisodeStatus(
            controller_episode_id=request.controller_episode_id,
            state="ready",
            scenario_id=request.selection.scenario_id,
            variant_id=request.selection.variant_id,
            difficulty=request.selection.difficulty,
            namespace=namespace,
            attacker_ready=True,
            target_services=target_services,
            active_flag_source=request.variant.flag_source,
        )
        self._episodes[request.controller_episode_id] = {
            "namespace": namespace,
            "access": attacker_access,
            "status": status,
        }
        return ProvisioningResult(attacker_access=attacker_access, status=status)

    def get_status(self, controller_episode_id: str) -> EpisodeStatus:
        episode = self._require_episode(controller_episode_id)
        namespace = str(episode["namespace"])
        try:
            deployments = ["redteam", "helpdesk-web", "internal-api"]
            ready = all(self._deployment_available(namespace, deployment) for deployment in deployments)
            status = episode["status"]
            status.state = "ready" if ready else "provisioning"
            status.attacker_ready = ready
            return status
        except subprocess.CalledProcessError:
            status = episode["status"]
            status.state = "failed"
            status.attacker_ready = False
            return status

    def get_attacker_access(self, controller_episode_id: str) -> AttackerAccess:
        return self._require_episode(controller_episode_id)["access"]

    def terminate_episode(self, controller_episode_id: str) -> None:
        episode = self._require_episode(controller_episode_id)
        namespace = str(episode["namespace"])
        self._kubectl(["delete", "namespace", namespace, "--ignore-not-found=true", "--wait=false"])
        self._episodes.pop(controller_episode_id, None)

    def _require_episode(self, controller_episode_id: str) -> dict[str, Any]:
        episode = self._episodes.get(controller_episode_id)
        if episode is None:
            raise KeyError(f"Unknown provisioned episode: {controller_episode_id}")
        return episode

    def _ensure_cluster(self) -> None:
        if self.cluster_name in self._kind_clusters():
            return
        if not self.auto_create_cluster:
            raise RuntimeError(f"kind cluster '{self.cluster_name}' does not exist.")
        self.runner.run(
            [self.kind_path, "create", "cluster", "--name", self.cluster_name],
            check=True,
        )

    def _kind_clusters(self) -> list[str]:
        result = self.runner.run([self.kind_path, "get", "clusters"], check=False)
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _kubectl(self, args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return self.runner.run(
            [self.kubectl_path, "--context", self.kubectl_context, *args],
            input_text=input_text,
            check=True,
        )

    def _kubectl_apply(self, manifest: str) -> None:
        self._kubectl(["apply", "-f", "-"], input_text=manifest)

    def _deployment_available(self, namespace: str, deployment: str) -> bool:
        result = self._kubectl(
            [
                "get",
                "deployment",
                "-n",
                namespace,
                deployment,
                "-o",
                "jsonpath={.status.availableReplicas}",
            ]
        )
        return (result.stdout or "").strip() == "1"

    def _build_cluster_service_endpoints(self, request: ProvisioningRequest) -> list[RemoteServiceEndpoint]:
        namespace = request.layout.namespace
        services: list[RemoteServiceEndpoint] = []
        for endpoint in request.layout.targets[0].exposed_services:
            host = "helpdesk-web" if endpoint.service_id == "helpdesk-web" else "internal-api"
            entrypoint_path = endpoint.entrypoint_path
            if endpoint.service_id == "helpdesk-web":
                entrypoint_path = "/helpdesk"
            elif endpoint.service_id == "debug-status":
                entrypoint_path = "/internal-api/v1/status"
            elif endpoint.service_id == "ops-review":
                entrypoint_path = "/ops/artifacts"
            services.append(
                RemoteServiceEndpoint(
                    service_id=endpoint.service_id,
                    display_name=endpoint.display_name,
                    host=f"{host}.{namespace}.svc.cluster.local",
                    port=80 if host == "helpdesk-web" else 8080,
                    protocol=endpoint.protocol,
                    exposure="cluster_internal",
                    entrypoint_path=entrypoint_path,
                    notes=endpoint.notes,
                )
            )
        return services

    def _build_episode_manifest(self, request: ProvisioningRequest, namespace: str) -> str:
        helpdesk_data = {
            "tickets": [ticket.model_dump() for ticket in request.seed_bundle.tickets],
            "search_mode": request.variant.search_mode,
            "flag_source": request.variant.flag_source,
            "flag_value": request.seed_bundle.flag_value,
            "source_manifest": "k8s/configmap-init-sql.yaml",
        }
        internal_data = {
            "exploit_path": request.variant.exploit_path,
            "internal_status": request.seed_bundle.internal_status,
            "artifacts": request.rendered_artifacts,
        }
        helpdesk_json = json.dumps(helpdesk_data, indent=2, sort_keys=True)
        internal_json = json.dumps(internal_data, indent=2, sort_keys=True)
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: episode-assets
  namespace: {namespace}
data:
  helpdesk_app.py: |
{indent(HELPDESK_APP.rstrip(), '    ')}
  internal_app.py: |
{indent(INTERNAL_APP.rstrip(), '    ')}
  helpdesk-data.json: |
{indent(helpdesk_json, '    ')}
  internal-data.json: |
{indent(internal_json, '    ')}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redteam
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redteam
  template:
    metadata:
      labels:
        app: redteam
    spec:
      containers:
        - name: redteam
          image: {self.attacker_image}
          command: ["/bin/sh", "-c", "sleep infinity"]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: helpdesk-web
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: helpdesk-web
  template:
    metadata:
      labels:
        app: helpdesk-web
    spec:
      containers:
        - name: helpdesk-web
          image: {self.app_image}
          command: ["python", "/opt/episode/helpdesk_app.py"]
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: episode-assets
              mountPath: /opt/episode
      volumes:
        - name: episode-assets
          configMap:
            name: episode-assets
---
apiVersion: v1
kind: Service
metadata:
  name: helpdesk-web
  namespace: {namespace}
spec:
  selector:
    app: helpdesk-web
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: internal-api
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: internal-api
  template:
    metadata:
      labels:
        app: internal-api
    spec:
      containers:
        - name: internal-api
          image: {self.app_image}
          command: ["python", "/opt/episode/internal_app.py"]
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: episode-assets
              mountPath: /opt/episode
      volumes:
        - name: episode-assets
          configMap:
            name: episode-assets
---
apiVersion: v1
kind: Service
metadata:
  name: internal-api
  namespace: {namespace}
spec:
  selector:
    app: internal-api
  ports:
    - port: 8080
      targetPort: 8080
"""
