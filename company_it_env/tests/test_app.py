from __future__ import annotations

from fastapi.testclient import TestClient


def test_control_plane_and_simulated_target_routes(client: TestClient, controller) -> None:  # type: ignore[no-untyped-def]
    provision = controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="app-episode",
    )

    health = client.get("/controller/health")
    assert health.status_code == 200
    assert health.json()["controller_mode"] == "simulated"

    status = client.get("/episodes/app-episode/status")
    assert status.status_code == 200
    assert status.json()["variant_id"] == "helpdesk_easy_union"

    access = client.get("/episodes/app-episode/attacker-access")
    assert access.status_code == 200
    assert access.json()["workspace_label"].startswith("redteam-")

    helpdesk = client.get(provision.brief.public_url_path)
    assert helpdesk.status_code == 200
    assert "Northbridge Support Portal" in helpdesk.text

    search = client.get(f"/simulated-target/app-episode/helpdesk/api/search", params={"query": "vpn"})
    assert search.status_code == 200
    payload = search.json()
    assert payload["rows"][0]["title"] == "vpn-profile-reset"


def test_submission_requires_episode_context(client: TestClient, controller) -> None:  # type: ignore[no-untyped-def]
    controller.create_episode(
        seed=0,
        scenario_id="helpdesk",
        difficulty="easy",
        controller_episode_id="submit-episode",
    )

    submit = client.post(
        "/challenge/submit",
        json={"episode_id": "submit-episode", "flag": "flag{wrong}"},
    )
    assert submit.status_code == 200
    result = submit.json()
    assert result["accepted"] is False
    assert result["reward"] == 0.0
