from __future__ import annotations

import subprocess

from company_it_env.server.controller import ProvisionerBackedLabController
from company_it_env.server.kind_provisioner import KindRangeProvisioner


class FakeRunner:
    def __init__(self, *, clusters: list[str] | None = None) -> None:
        self.clusters = clusters or []
        self.calls: list[tuple[list[str], str | None, bool]] = []

    def run(self, command: list[str], *, input_text: str | None = None, check: bool = True):  # type: ignore[no-untyped-def]
        self.calls.append((command, input_text, check))
        if command[:3] == ["kind", "get", "clusters"]:
            return subprocess.CompletedProcess(command, 0, stdout="\n".join(self.clusters), stderr="")
        if command[:3] == ["kind", "create", "cluster"]:
            name = command[-1]
            if name not in self.clusters:
                self.clusters.append(name)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[0] == "kubectl":
            if "jsonpath={.status.availableReplicas}" in command:
                return subprocess.CompletedProcess(command, 0, stdout="1", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        raise AssertionError(f"Unexpected command: {command}")


def test_kind_provisioner_creates_kubectl_manifests(tmp_path) -> None:
    runner = FakeRunner(clusters=["openenv-range"])
    provisioner = KindRangeProvisioner(cluster_name="openenv-range", runner=runner)
    controller = ProvisionerBackedLabController(provisioner, output_root=tmp_path / "controller")

    result = controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="kind-episode",
    )

    assert result.attacker_access.bootstrap_commands[0].startswith(
        "kubectl --context kind-openenv-range exec -it -n episode-kind-epi deploy/redteam -- bash"
    )
    assert result.attacker_access.target_services[0].entrypoint_path == "/helpdesk"
    assert any(
        command[:6] == ["kubectl", "--context", "kind-openenv-range", "apply", "-f", "-"]
        and input_text is not None
        and "kind: Deployment" in input_text
        for command, input_text, _ in runner.calls
    )

    status = controller.get_status("kind-episode")
    assert status.state == "ready"
    controller.terminate_episode("kind-episode")
    assert any("delete" in command for command, _, _ in runner.calls)


def test_kind_provisioner_auto_creates_cluster(tmp_path) -> None:
    runner = FakeRunner(clusters=[])
    provisioner = KindRangeProvisioner(cluster_name="autocreate", runner=runner)
    controller = ProvisionerBackedLabController(provisioner, output_root=tmp_path / "controller")

    controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="auto-episode",
    )

    assert any(command[:3] == ["kind", "create", "cluster"] for command, _, _ in runner.calls)
