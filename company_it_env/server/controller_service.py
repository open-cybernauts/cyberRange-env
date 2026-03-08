"""Standalone FastAPI service for the remote lab controller contract."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from company_it_env.models import EpisodeCreateRequest, FlagSubmission
from company_it_env.server.controller import (
    HttpRangeProvisioner,
    LabController,
    ProvisionerBackedLabController,
    SimulatedLabController,
)
from company_it_env.server.kind_provisioner import KindRangeProvisioner


def build_controller_from_env(output_root: Path | None = None) -> LabController:
    backend = os.environ.get("COMPANY_IT_CONTROLLER_BACKEND", "simulated").strip().lower()
    controller_output_root = output_root or (Path(__file__).resolve().parents[1] / "outputs" / "controller_service")
    if backend == "simulated":
        return SimulatedLabController(output_root=controller_output_root)
    if backend == "provisioner":
        provisioner_url = os.environ.get("COMPANY_IT_PROVISIONER_URL")
        if not provisioner_url:
            raise RuntimeError(
                "COMPANY_IT_PROVISIONER_URL is required when COMPANY_IT_CONTROLLER_BACKEND=provisioner."
            )
        provisioner = HttpRangeProvisioner(
            provisioner_url,
            api_token=os.environ.get("COMPANY_IT_PROVISIONER_TOKEN"),
        )
        return ProvisionerBackedLabController(provisioner, output_root=controller_output_root)
    if backend == "kind":
        return ProvisionerBackedLabController(
            KindRangeProvisioner(
                cluster_name=os.environ.get("COMPANY_IT_KIND_CLUSTER", "openenv-range"),
                auto_create_cluster=os.environ.get("COMPANY_IT_KIND_AUTO_CREATE", "true").lower()
                not in {"0", "false", "no"},
            ),
            output_root=controller_output_root,
        )
    raise RuntimeError(f"Unsupported controller backend: {backend}")


def build_controller_app(controller: LabController | None = None) -> FastAPI:
    controller_instance = controller or SimulatedLabController()
    app = FastAPI(title="company_it_env_controller")

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse(controller_instance.health().model_dump())

    @app.get("/scenarios")
    def list_scenarios() -> JSONResponse:
        return JSONResponse(controller_instance.list_scenarios())

    @app.post("/episodes")
    def create_episode(request: EpisodeCreateRequest) -> JSONResponse:
        provision = controller_instance.create_episode(
            seed=request.seed,
            scenario_id=request.scenario_id,
            difficulty=request.difficulty,
            controller_episode_id=request.controller_episode_id,
        )
        return JSONResponse(provision.model_dump())

    @app.get("/episodes/{episode_id}/status")
    def get_status(episode_id: str) -> JSONResponse:
        try:
            status = controller_instance.get_status(episode_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(status.model_dump())

    @app.get("/episodes/{episode_id}/attacker-access")
    def get_attacker_access(episode_id: str) -> JSONResponse:
        try:
            access = controller_instance.get_attacker_access(episode_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(access.model_dump())

    @app.post("/episodes/{episode_id}/submit")
    def submit_flag(episode_id: str, submission: FlagSubmission) -> JSONResponse:
        try:
            result = controller_instance.submit_flag(episode_id, submission.flag)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(result.model_dump())

    @app.delete("/episodes/{episode_id}")
    def terminate_episode(episode_id: str) -> JSONResponse:
        try:
            controller_instance.terminate_episode(episode_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse({"terminated": True, "episode_id": episode_id})

    return app


app = build_controller_app(build_controller_from_env())


def main() -> None:
    import uvicorn

    uvicorn.run(
        build_controller_app(build_controller_from_env()),
        host="0.0.0.0",
        port=8010,
    )


if __name__ == "__main__":
    main()
