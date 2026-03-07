"""Validation harness for OpenEnv and RL-readiness checks."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction

from company_it_env.server.company_it_environment import CompanyITEnvironment
from company_it_env.server.lab_runtime import LabRuntime


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _replay_action(action_data: dict[str, Any]) -> ListToolsAction | CallToolAction:
    action_type = action_data.get("type")
    if action_type == "list_tools":
        return ListToolsAction(**action_data)
    if action_type == "call_tool":
        return CallToolAction(**action_data)
    raise ValueError(f"Unsupported replay action type: {action_type}")


def _normalize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    result = observation.get("result")
    if hasattr(result, "data") and isinstance(result.data, dict):
        result = result.data
    elif hasattr(result, "structured_content") and isinstance(result.structured_content, dict):
        result = result.structured_content
    return {
        "done": observation.get("done"),
        "reward": observation.get("reward"),
        "metadata": observation.get("metadata"),
        "tool_name": observation.get("tool_name"),
        "result": result,
        "tools": observation.get("tools"),
    }


def run_validation(output_root: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_output_root = output_root or (Path(tmp_dir) / "outputs")

        runtime_a = LabRuntime(output_root=base_output_root / "run_a")
        env_a = CompanyITEnvironment(runtime=runtime_a, max_episode_steps=4)
        reset_a = env_a.reset(
            seed=0,
            episode_id="determinism-a",
            scenario_id="helpdesk",
            difficulty="easy",
        ).model_dump()
        search_a = runtime_a.search_tickets("vpn").model_dump()
        artifacts_a = {
            path: runtime_a.read_artifact(path)
            for path in ("k8s/configmap-init-sql.yaml", "k8s/internal-api.yaml")
        }

        runtime_b = LabRuntime(output_root=base_output_root / "run_b")
        env_b = CompanyITEnvironment(runtime=runtime_b, max_episode_steps=4)
        reset_b = env_b.reset(
            seed=0,
            episode_id="determinism-b",
            scenario_id="helpdesk",
            difficulty="easy",
        ).model_dump()
        search_b = runtime_b.search_tickets("vpn").model_dump()
        artifacts_b = {
            path: runtime_b.read_artifact(path)
            for path in ("k8s/configmap-init-sql.yaml", "k8s/internal-api.yaml")
        }

        checks.append(
            _check(
                "deterministic_reset",
                reset_a["metadata"]["brief"] == reset_b["metadata"]["brief"]
                and search_a == search_b
                and artifacts_a == artifacts_b,
                "Reset, search results, and rendered artifacts match across runs with the same seed.",
            )
        )

        schema_ok = (
            sorted(reset_a.keys()) == sorted(reset_b.keys())
            and sorted(reset_a["metadata"].keys()) == sorted(reset_b["metadata"].keys())
        )
        checks.append(
            _check(
                "stable_observation_schema",
                schema_ok,
                "Reset observations expose a stable top-level and metadata schema.",
            )
        )

        variant_runtime = LabRuntime(output_root=base_output_root / "variant")
        variant_env = CompanyITEnvironment(runtime=variant_runtime, max_episode_steps=4)
        variant_reset = variant_env.reset(
            seed=5,
            episode_id="variant-check",
            scenario_id="internal_ops",
            difficulty="hard",
        ).model_dump()
        variant_ok = (
            variant_reset["metadata"]["brief"]["scenario_id"] == "internal_ops"
            and variant_reset["metadata"]["brief"]["difficulty"] == "hard"
            and variant_reset["metadata"]["brief"]["variant_id"] == "internal_ops_hard_debug_chain"
        )
        checks.append(
            _check(
                "seed_stable_variant_selection",
                variant_ok,
                "Reset filters and seed select the expected deterministic variant.",
            )
        )

        reward_runtime = LabRuntime(output_root=base_output_root / "reward")
        reward_env = CompanyITEnvironment(runtime=reward_runtime, max_episode_steps=4)
        reward_env.reset(
            seed=0,
            episode_id="reward-check",
            scenario_id="helpdesk",
            difficulty="easy",
        )
        artifact_reward = reward_env.step(
            CallToolAction(tool_name="inspect_artifact", arguments={"path": "k8s/configmap-init-sql.yaml"})
        )
        wrong = reward_env.step(CallToolAction(tool_name="submit_flag", arguments={"flag": "flag{wrong}"}))
        correct = reward_env.step(
            CallToolAction(
                tool_name="submit_flag",
                arguments={"flag": reward_runtime.current_flag},
            )
        )
        reward_ok = (
            artifact_reward.reward == 0.2
            and artifact_reward.done is False
            and wrong.reward == 0.0
            and wrong.done is False
            and correct.reward == 1.0
            and correct.done is True
        )
        checks.append(
            _check(
                "reward_and_done_surface",
                reward_ok,
                "Top-level observations now expose reward/done for submit_flag.",
            )
        )

        bounded_runtime = LabRuntime(output_root=base_output_root / "bounded")
        bounded_env = CompanyITEnvironment(runtime=bounded_runtime, max_episode_steps=2)
        bounded_env.reset(seed=0, episode_id="bounded-check", scenario_id="helpdesk", difficulty="easy")
        bounded_env.step(ListToolsAction())
        bounded = bounded_env.step(ListToolsAction())
        bounded_ok = bounded.done is True and bounded.metadata.get("truncated") is True
        checks.append(
            _check(
                "bounded_episode_length",
                bounded_ok,
                "Episodes terminate with truncation once max_episode_steps is reached.",
            )
        )

        replay_runtime = LabRuntime(output_root=base_output_root / "replay")
        replay_env = CompanyITEnvironment(runtime=replay_runtime, max_episode_steps=5)
        replay_env.reset(seed=0, episode_id="replay-source", scenario_id="helpdesk", difficulty="easy")
        source_observations = [
            replay_env.step(ListToolsAction()).model_dump(),
            replay_env.step(
                CallToolAction(
                    tool_name="inspect_artifact",
                    arguments={"path": "k8s/configmap-init-sql.yaml"},
                )
            ).model_dump(),
            replay_env.step(CallToolAction(tool_name="challenge_brief", arguments={})).model_dump(),
            replay_env.step(
                CallToolAction(
                    tool_name="submit_flag",
                    arguments={"flag": replay_runtime.current_flag},
                )
            ).model_dump(),
        ]
        trajectory_path = replay_env.trajectory_path
        replay_ok = False
        replay_details = "Trajectory file was not created."
        if trajectory_path is not None and trajectory_path.exists():
            entries = _read_jsonl(trajectory_path)
            step_entries = [entry for entry in entries if entry["event"] == "step"]
            fresh_runtime = LabRuntime(output_root=base_output_root / "replay-fresh")
            fresh_env = CompanyITEnvironment(runtime=fresh_runtime, max_episode_steps=5)
            fresh_env.reset(seed=0, episode_id="replay-fresh", scenario_id="helpdesk", difficulty="easy")
            replayed = [
                fresh_env.step(_replay_action(entry["action"])).model_dump()
                for entry in step_entries
            ]
            replay_ok = all(
                _normalize_observation(logged) == _normalize_observation(current)
                for logged, current in zip(source_observations, replayed, strict=True)
            )
            replay_details = "Saved trajectories can be replayed against the same scenario version."
        checks.append(_check("trajectory_replay", replay_ok, replay_details))

        seed_delta_runtime_a = LabRuntime(output_root=base_output_root / "seed-delta-a")
        seed_delta_runtime_a.reset(seed=0, scenario_id="internal_ops", difficulty="easy")
        seed_delta_runtime_b = LabRuntime(output_root=base_output_root / "seed-delta-b")
        seed_delta_runtime_b.reset(seed=1, scenario_id="internal_ops", difficulty="easy")
        seed_delta_ok = (
            seed_delta_runtime_a.current_flag != seed_delta_runtime_b.current_flag
            or seed_delta_runtime_a.read_artifact("k8s/internal-api.yaml")
            != seed_delta_runtime_b.read_artifact("k8s/internal-api.yaml")
        )
        checks.append(
            _check(
                "controlled_seed_variation",
                seed_delta_ok,
                "Different seeds produce controlled changes in flags or rendered artifact values.",
            )
        )

    passed = all(check["passed"] for check in checks)
    return {"passed": passed, "checks": checks}


def main() -> None:
    report = run_validation()
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] {check['name']}: {check['details']}")

    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
