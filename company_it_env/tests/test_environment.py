from __future__ import annotations

import json
from pathlib import Path

from company_it_env import CallToolAction, ListToolsAction
from company_it_env.server.company_it_environment import CompanyITEnvironment
from company_it_env.server.lab_runtime import LabRuntime


def test_environment_surfaces_reward_done_and_logs(tmp_path: Path) -> None:
    runtime = LabRuntime(output_root=tmp_path / "outputs")
    env = CompanyITEnvironment(runtime=runtime, max_episode_steps=4)

    reset = env.reset(seed=0, episode_id="episode-a", scenario_id="helpdesk", difficulty="easy")
    assert reset.reward == 0.0
    assert reset.done is False
    assert reset.metadata["brief"]["objective"].startswith("Recover the production flag")
    assert reset.metadata["brief"]["scenario_id"] == "helpdesk"
    assert reset.metadata["variant_id"] == "helpdesk_easy_union"

    tools = env.step(ListToolsAction())
    assert tools.done is False
    tool_names = {tool["name"] for tool in tools.model_dump()["tools"]}
    assert "submit_flag" in tool_names
    assert "list_scenarios" in tool_names

    artifact = env.step(
        CallToolAction(tool_name="inspect_artifact", arguments={"path": "k8s/configmap-init-sql.yaml"})
    )
    assert artifact.reward == 0.2
    assert artifact.done is False

    wrong = env.step(CallToolAction(tool_name="submit_flag", arguments={"flag": "flag{wrong}"}))
    assert wrong.reward == 0.0
    assert wrong.done is False

    correct = env.step(
        CallToolAction(
            tool_name="submit_flag",
            arguments={"flag": runtime.current_flag},
        )
    )
    assert correct.reward == 1.0
    assert correct.done is True
    assert correct.metadata["accepted"] is True

    trajectory_path = env.trajectory_path
    assert trajectory_path is not None and trajectory_path.exists()
    entries = [
        json.loads(line)
        for line in trajectory_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert entries[0]["event"] == "reset"
    assert entries[1]["event"] == "step"
    assert entries[-1]["observation"]["done"] is True
    assert entries[-1]["observation"]["reward"] == 1.0


def test_environment_truncates_after_max_steps(tmp_path: Path) -> None:
    runtime = LabRuntime(output_root=tmp_path / "outputs")
    env = CompanyITEnvironment(runtime=runtime, max_episode_steps=2)
    env.reset(seed=0, episode_id="episode-b", scenario_id="helpdesk", difficulty="easy")

    first = env.step(ListToolsAction())
    assert first.done is False

    second = env.step(ListToolsAction())
    assert second.done is True
    assert second.metadata["truncated"] is True
