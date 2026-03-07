from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from company_it_env.server.app import build_app
from company_it_env.server.lab_runtime import LabRuntime


@pytest.fixture
def runtime(tmp_path: Path) -> LabRuntime:
    return LabRuntime(output_root=tmp_path / "outputs")


@pytest.fixture
def client(runtime: LabRuntime) -> TestClient:
    app = build_app(runtime)
    with TestClient(app) as test_client:
        yield test_client
