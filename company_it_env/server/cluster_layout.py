"""Helpers for describing the remote cluster topology used by each episode."""

from __future__ import annotations

from company_it_env.models import (
    RemoteClusterLayout,
    RemoteDeploymentSpec,
    RemoteServiceEndpoint,
    ResetSelection,
    VariantDefinition,
)


def build_remote_cluster_layout(
    *,
    controller_episode_id: str,
    selection: ResetSelection,
    variant: VariantDefinition,
    manifest_values: dict[str, str],
) -> RemoteClusterLayout:
    namespace = f"episode-{controller_episode_id[:8]}"
    public_host = manifest_values.get("PUBLIC_HOST", f"target-{controller_episode_id[:8]}.lab.local")
    internal_service = manifest_values.get("INTERNAL_API_SERVICE", "internal-api")
    target_root = f"/simulated-target/{controller_episode_id}"

    public_services = [
        RemoteServiceEndpoint(
            service_id="helpdesk-web",
            display_name="Public Helpdesk",
            host=public_host,
            port=80,
            protocol="http",
            exposure="public",
            entrypoint_path=f"{target_root}/helpdesk",
            notes="Internet-facing application entrypoint for the scenario.",
        )
    ]

    if variant.exploit_path == "debug_endpoint_exposure":
        public_services.append(
            RemoteServiceEndpoint(
                service_id="debug-status",
                display_name="Leaked Debug Status",
                host=public_host,
                port=80,
                protocol="http",
                exposure="external_only",
                entrypoint_path=f"{target_root}/internal-api/v1/status",
                notes="Diagnostics surface unintentionally exposed outside the cluster.",
            )
        )
    elif variant.exploit_path == "credential_leak_from_manifest":
        public_services.append(
            RemoteServiceEndpoint(
                service_id="ops-review",
                display_name="Ops Review Surface",
                host=public_host,
                port=80,
                protocol="http",
                exposure="external_only",
                entrypoint_path=f"{target_root}/ops/artifacts/",
                notes="Configuration review surface with rendered deployment outputs.",
            )
        )

    return RemoteClusterLayout(
        namespace=namespace,
        redteam=RemoteDeploymentSpec(
            deployment_id=f"redteam-{selection.scenario_id}",
            role="redteam",
            namespace=namespace,
            image="ghcr.io/open-cybernauts/redteam-toolkit:latest",
            network_zone="attacker",
            notes=[
                "Contains bash and common reconnaissance tooling.",
                "Has network reachability only to the externally exposed target surfaces.",
            ],
        ),
        targets=[
            RemoteDeploymentSpec(
                deployment_id=f"helpdesk-{selection.scenario_id}",
                role="target",
                namespace=namespace,
                image="ghcr.io/northbridge/helpdesk-web:simulated",
                network_zone="dmz",
                exposed_services=public_services,
                notes=[
                    "Represents the internet-facing application tier.",
                ],
            ),
            RemoteDeploymentSpec(
                deployment_id=internal_service,
                role="target",
                namespace=namespace,
                image=manifest_values.get("API_IMAGE", "ghcr.io/northbridge/internal-api:simulated"),
                network_zone="internal",
                notes=[
                    "Represents cluster-internal service dependencies.",
                ],
            ),
        ],
    )
