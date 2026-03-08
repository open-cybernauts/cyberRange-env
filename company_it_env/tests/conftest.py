from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from company_it_env.server.app import build_app
from company_it_env.server.controller import SimulatedLabController


@pytest.fixture
def controller(tmp_path: Path) -> SimulatedLabController:
    return SimulatedLabController(output_root=tmp_path / "outputs")


@pytest.fixture
def client(controller: SimulatedLabController) -> TestClient:
    app = build_app(controller)
    with TestClient(app) as test_client:
        yield test_client
