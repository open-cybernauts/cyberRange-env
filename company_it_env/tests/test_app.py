from __future__ import annotations

from fastapi.testclient import TestClient


def test_helpdesk_endpoints(client: TestClient) -> None:
    helpdesk = client.get("/helpdesk")
    assert helpdesk.status_code == 200
    assert "Northbridge Support Portal" in helpdesk.text

    search = client.get("/helpdesk/api/search", params={"query": "vpn"})
    assert search.status_code == 200
    payload = search.json()
    assert payload["rows"][0]["title"] == "vpn-profile-reset"


def test_artifacts_and_submission(client: TestClient) -> None:
    artifacts = client.get("/artifacts")
    assert artifacts.status_code == 200
    artifact_paths = artifacts.json()["artifacts"]
    assert "sql/init.sql" in artifact_paths
    assert "k8s/configmap-init-sql.yaml" in artifact_paths

    submit = client.post("/challenge/submit", json={"flag": "flag{wrong}"})
    assert submit.status_code == 200
    result = submit.json()
    assert result["accepted"] is False
    assert result["reward"] == 0.0
