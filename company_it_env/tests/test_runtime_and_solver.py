from __future__ import annotations

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from company_it_env.server import solver
from company_it_env.server.lab_runtime import LabRuntime
from company_it_env.server.validate_rl_readiness import run_validation


def test_runtime_reset_and_seeded_search(runtime: LabRuntime) -> None:
    brief = runtime.reset(seed=0, scenario_id="helpdesk", difficulty="easy")
    assert brief.objective.startswith("Recover the production flag")
    assert brief.variant_id == "helpdesk_easy_union"

    search = runtime.search_tickets("vpn")
    assert search.error is None
    assert any(row.title == "vpn-profile-reset" for row in search.rows)


def test_solver_main_against_test_client(client: TestClient, monkeypatch, capsys) -> None:
    def fake_get(url: str, params=None, timeout=None):  # type: ignore[no-untyped-def]
        del timeout
        path = urlparse(url).path
        return client.get(path, params=params)

    def fake_post(url: str, json=None, timeout=None):  # type: ignore[no-untyped-def]
        del timeout
        path = urlparse(url).path
        return client.post(path, json=json)

    monkeypatch.setattr(solver.requests, "get", fake_get)
    monkeypatch.setattr(solver.requests, "post", fake_post)
    monkeypatch.setenv("LAB_BASE_URL", "http://testserver")

    solver.main()

    captured = capsys.readouterr()
    assert "Recovered flag{company_it_env_support_ticket_flag}" in captured.out
    assert "'accepted': True" in captured.out


def test_rl_readiness_harness_passes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report = run_validation(output_root=tmp_path / "validation")
    assert report["passed"] is True
