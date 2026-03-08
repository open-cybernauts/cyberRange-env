from __future__ import annotations

from fastapi.testclient import TestClient

from company_it_env.server import solver
from company_it_env.server.controller import SimulatedLabController
from company_it_env.server.validate_rl_readiness import run_validation


def test_controller_reset_and_seeded_topology(controller: SimulatedLabController) -> None:
    provision = controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="solver-episode",
    )
    assert provision.brief.objective.startswith("From the attacker environment")
    assert provision.brief.variant_id == "helpdesk_easy_union"
    assert provision.attacker_access.target_services[0].service_id == "helpdesk-web"


def test_solver_helpers_against_test_client(client: TestClient, controller: SimulatedLabController) -> None:
    provision = controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="solver-http",
    )
    public_base = "http://testserver/simulated-target/solver-http"

    def fake_get(url: str, params=None, timeout=None):  # type: ignore[no-untyped-def]
        del timeout
        assert url == f"{public_base}/helpdesk/api/search"
        return client.get("/simulated-target/solver-http/helpdesk/api/search", params=params)

    def fake_post(url: str, json=None, timeout=None):  # type: ignore[no-untyped-def]
        del timeout
        assert url == "http://testserver/challenge/submit"
        return client.post("/challenge/submit", json=json)

    solver.requests.get = fake_get
    solver.requests.post = fake_post

    flag = solver.recover_flag_from_public_search(public_base)
    result = solver.submit_flag("http://testserver", provision.controller_episode_id, flag)
    assert flag == "flag{company_it_env_support_ticket_flag}"
    assert result["accepted"] is True


def test_rl_readiness_harness_passes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report = run_validation(output_root=tmp_path / "validation")
    assert report["passed"] is True
