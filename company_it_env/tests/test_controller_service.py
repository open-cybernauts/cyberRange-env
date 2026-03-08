from __future__ import annotations

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from company_it_env.models import AttackerAccess, EpisodeStatus, ProvisioningResult
from company_it_env.server.controller import (
    HttpLabControllerClient,
    ProvisionerBackedLabController,
    RangeProvisioner,
    SimulatedLabController,
)
from company_it_env.server.controller_service import build_controller_app, build_controller_from_env


class FakeProvisioner(RangeProvisioner):
    def __init__(self) -> None:
        self.remote_url = "http://provisioner.test"
        self._access: dict[str, AttackerAccess] = {}
        self._status: dict[str, EpisodeStatus] = {}

    def health(self) -> dict[str, object]:
        return {"status": "ok", "backend": "fake"}

    def provision_episode(self, request) -> ProvisioningResult:  # type: ignore[no-untyped-def]
        target_services = request.layout.targets[0].exposed_services
        access = AttackerAccess(
            connection_type="ssh",
            workspace_label=f"rt-{request.controller_episode_id[:8]}",
            host="redteam.remote.example",
            username="operator",
            port=22,
            reachable_hosts=[service.host for service in target_services],
            target_services=target_services,
            constraints=["Network-only target access."],
        )
        status = EpisodeStatus(
            controller_episode_id=request.controller_episode_id,
            state="ready",
            scenario_id=request.selection.scenario_id,
            variant_id=request.selection.variant_id,
            difficulty=request.selection.difficulty,
            namespace=request.layout.namespace,
            attacker_ready=True,
            target_services=target_services,
            active_flag_source=request.variant.flag_source,
        )
        self._access[request.controller_episode_id] = access
        self._status[request.controller_episode_id] = status
        return ProvisioningResult(attacker_access=access, status=status)

    def get_status(self, controller_episode_id: str) -> EpisodeStatus:
        return self._status[controller_episode_id]

    def get_attacker_access(self, controller_episode_id: str) -> AttackerAccess:
        return self._access[controller_episode_id]

    def terminate_episode(self, controller_episode_id: str) -> None:
        self._access.pop(controller_episode_id, None)
        self._status.pop(controller_episode_id, None)


def test_http_lab_controller_client_contract(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    controller_backend = SimulatedLabController(output_root=tmp_path / "controller")
    app = build_controller_app(controller_backend)

    with TestClient(app) as test_client:

        def fake_get(url: str, timeout=None):  # type: ignore[no-untyped-def]
            del timeout
            return test_client.get(urlparse(url).path)

        def fake_post(url: str, json=None, timeout=None):  # type: ignore[no-untyped-def]
            del timeout
            return test_client.post(urlparse(url).path, json=json)

        def fake_delete(url: str, timeout=None):  # type: ignore[no-untyped-def]
            del timeout
            return test_client.delete(urlparse(url).path)

        monkeypatch.setattr("company_it_env.server.controller.requests.get", fake_get)
        monkeypatch.setattr("company_it_env.server.controller.requests.post", fake_post)
        monkeypatch.setattr("company_it_env.server.controller.requests.delete", fake_delete)

        client = HttpLabControllerClient("http://controller.test", output_root=tmp_path / "client")

        health = client.health()
        assert health.controller_mode == "simulated"

        scenarios = client.list_scenarios()
        assert any(scenario["scenario_id"] == "helpdesk" for scenario in scenarios)

        provision = client.create_episode(
            seed=0,
            scenario_id="helpdesk",
            difficulty="easy",
            controller_episode_id="http-episode",
        )
        assert provision.controller_episode_id == "http-episode"
        assert provision.brief.variant_id == "helpdesk_easy_union"

        access = client.get_attacker_access("http-episode")
        assert access.workspace_label.startswith("redteam-")
        assert access.target_services

        status = client.get_status("http-episode")
        assert status.state == "ready"
        assert status.variant_id == "helpdesk_easy_union"

        result = client.submit_flag("http-episode", controller_backend.current_flag_for_testing("http-episode"))
        assert result.accepted is True
        assert result.done is True

        client.terminate_episode("http-episode")


def test_controller_service_returns_404_for_unknown_episode(tmp_path) -> None:
    app = build_controller_app(SimulatedLabController(output_root=tmp_path / "controller"))

    with TestClient(app) as test_client:
        response = test_client.get("/episodes/missing/status")
        assert response.status_code == 404
        assert response.json()["detail"] == "Episode not found"


def test_provisioner_backed_controller_service_flow(tmp_path) -> None:
    controller = ProvisionerBackedLabController(FakeProvisioner(), output_root=tmp_path / "controller")
    app = build_controller_app(controller)

    with TestClient(app) as test_client:
        created = test_client.post(
            "/episodes",
            json={
                "seed": 0,
                "scenario_id": "helpdesk",
                "difficulty": "easy",
                "controller_episode_id": "prov-episode",
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["controller_episode_id"] == "prov-episode"
        assert payload["attacker_access"]["connection_type"] == "ssh"

        status = test_client.get("/episodes/prov-episode/status")
        assert status.status_code == 200
        assert status.json()["state"] == "ready"

        submit = test_client.post(
            "/episodes/prov-episode/submit",
            json={"flag": controller.current_flag_for_testing("prov-episode")},
        )
        assert submit.status_code == 200
        assert submit.json()["accepted"] is True


def test_build_controller_from_env_selects_provisioner(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COMPANY_IT_CONTROLLER_BACKEND", "provisioner")
    monkeypatch.setenv("COMPANY_IT_PROVISIONER_URL", "http://provisioner.test")

    class DummyProvisioner(FakeProvisioner):
        def __init__(self, base_url: str, timeout_s: float = 20.0, api_token: str | None = None) -> None:
            super().__init__()
            self.remote_url = base_url
            self.api_token = api_token

    monkeypatch.setattr(
        "company_it_env.server.controller_service.HttpRangeProvisioner",
        DummyProvisioner,
    )

    controller = build_controller_from_env(tmp_path / "controller")
    assert isinstance(controller, ProvisionerBackedLabController)
    assert controller.provisioner.remote_url == "http://provisioner.test"


def test_build_controller_from_env_selects_kind(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COMPANY_IT_CONTROLLER_BACKEND", "kind")
    monkeypatch.setenv("COMPANY_IT_KIND_CLUSTER", "local-range")
    monkeypatch.setenv("COMPANY_IT_KIND_AUTO_CREATE", "false")

    class DummyKindProvisioner(FakeProvisioner):
        def __init__(self, cluster_name: str = "openenv-range", auto_create_cluster: bool = True) -> None:
            super().__init__()
            self.remote_url = f"kind://{cluster_name}"
            self.cluster_name = cluster_name
            self.auto_create_cluster = auto_create_cluster

    monkeypatch.setattr(
        "company_it_env.server.controller_service.KindRangeProvisioner",
        DummyKindProvisioner,
    )

    controller = build_controller_from_env(tmp_path / "controller")
    assert isinstance(controller, ProvisionerBackedLabController)
    assert controller.provisioner.remote_url == "kind://local-range"
