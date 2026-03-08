"""OpenEnv environment implementation for the company IT lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastmcp import FastMCP
from pydantic import Field, model_validator

from company_it_env.server.controller import LabController, SimulatedLabController
from company_it_env.server.trajectory_logger import TrajectoryLogger

try:
    from openenv.core.env_server.mcp_environment import MCPEnvironment
    from openenv.core.env_server.mcp_types import (
        CallToolAction,
        CallToolObservation,
        ListToolsAction,
    )
    from openenv.core.env_server.types import Action, Observation, State
except Exception:  # pragma: no cover - dependency resolved in environment runtime
    MCPEnvironment = object  # type: ignore[assignment]

    class Action:  # type: ignore[no-redef]
        pass

    class Observation:  # type: ignore[no-redef]
        def __init__(self, done: bool, reward: float, metadata: dict[str, Any]) -> None:
            self.done = done
            self.reward = reward
            self.metadata = metadata

    class State:  # type: ignore[no-redef]
        def __init__(self, episode_id: str, step_count: int) -> None:
            self.episode_id = episode_id
            self.step_count = step_count

    class CallToolAction(Action):  # type: ignore[no-redef]
        def __init__(self, tool_name: str = "", arguments: dict[str, Any] | None = None) -> None:
            self.tool_name = tool_name
            self.arguments = arguments or {}

    class ListToolsAction(Action):  # type: ignore[no-redef]
        pass

    class CallToolObservation(Observation):  # type: ignore[no-redef]
        def __init__(
            self,
            tool_name: str,
            result: Any = None,
            error: Any = None,
            done: bool = False,
            reward: float = 0.0,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            super().__init__(done=done, reward=reward, metadata=metadata or {})
            self.tool_name = tool_name
            self.result = result
            self.error = error


class MCPWebAction(Action):
    """Action schema for the manual web UI."""

    type: Literal["call_tool", "list_tools"] = Field(
        default="call_tool", description="Action type discriminator"
    )
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool to call"
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments to pass to the tool"
    )

    @model_validator(mode="after")
    def validate_action(self) -> "MCPWebAction":
        if self.type == "call_tool" and not self.tool_name:
            raise ValueError("tool_name is required when type is 'call_tool'")
        return self


class CompanyITEnvironment(MCPEnvironment):
    """MCP-backed control plane for the hybrid remote-lab environment."""

    def __init__(
        self,
        controller: LabController | None = None,
        *,
        max_episode_steps: int = 25,
        trajectory_logger: TrajectoryLogger | None = None,
    ) -> None:
        self.controller = controller or SimulatedLabController()
        self.max_episode_steps = max_episode_steps
        self.trajectory_logger = trajectory_logger or TrajectoryLogger(self.controller.output_root)
        mcp = FastMCP("company_it_env")
        self._brief: dict[str, Any] | None = None
        self._controller_episode_id: str | None = None

        @mcp.tool
        def challenge_brief() -> dict[str, Any]:
            """Return the active scenario objective and exposed attack surface summary."""

            if self._brief is None:
                raise RuntimeError("Environment has not been reset yet.")
            return dict(self._brief)

        @mcp.tool
        def get_attacker_access() -> dict[str, Any]:
            """Return the attacker workspace details and reachable target services."""

            return self.controller.get_attacker_access(self._require_controller_episode_id()).model_dump()

        @mcp.tool
        def submit_flag(flag: str) -> dict[str, Any]:
            """Submit a recovered flag and receive reward metadata."""

            result = self.controller.submit_flag(self._require_controller_episode_id(), flag)
            return result.model_dump()

        @mcp.tool
        def episode_status() -> dict[str, Any]:
            """Return current controller-side episode status and exposed services."""

            return self.controller.get_status(self._require_controller_episode_id()).model_dump()

        @mcp.tool
        def list_scenarios() -> list[dict[str, Any]]:
            """List scenario families and their available variants."""

            return self.controller.list_scenarios()

        super().__init__(mcp)
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._seed: int | None = None
        self._has_reset = False
        self._terminated = False

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        difficulty: Optional[str] = None,
        **kwargs: Any,
    ) -> Observation:
        del kwargs
        if self._controller_episode_id is not None and not self._terminated:
            self.controller.terminate_episode(self._controller_episode_id)
        self._seed = seed
        self._has_reset = True
        self._terminated = False
        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
        provision = self.controller.create_episode(
            seed=seed,
            scenario_id=scenario_id,
            difficulty=difficulty,
            controller_episode_id=str(self._state.episode_id),
        )
        self._controller_episode_id = provision.controller_episode_id
        brief = provision.brief
        self._brief = brief.model_dump()
        observation = Observation(
            done=False,
            reward=0.0,
            metadata={
                "status": "ready",
                "brief": self._brief,
                "controller_episode_id": provision.controller_episode_id,
                "scenario_id": brief.scenario_id,
                "variant_id": brief.variant_id,
                "difficulty": brief.difficulty,
                "max_episode_steps": self.max_episode_steps,
            },
        )
        self.trajectory_logger.start_episode(
            episode_id=str(self._state.episode_id),
            seed=seed,
            observation=observation,
            state=self._state_dict(),
        )
        return observation

    def _step_impl(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> Observation:
        del timeout_s, kwargs
        return Observation(
            done=False,
            reward=0.0,
            metadata={
                "error": (
                    f"Unknown action type: {type(action).__name__}. "
                    "Use ListToolsAction or CallToolAction for MCP interactions."
                )
            },
        )

    def step(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> Observation:
        action = self._coerce_mcp_action(action)
        if isinstance(action, ListToolsAction) and not self._has_reset:
            observation = super().step(action, timeout_s=timeout_s, **kwargs)
            return self._normalize_observation(action, observation)

        if self._terminated:
            return Observation(
                done=True,
                reward=0.0,
                metadata={"error": "Episode already finished. Call reset() before stepping again."},
            )
        self._state.step_count += 1
        observation = super().step(action, timeout_s=timeout_s, **kwargs)
        observation = self._normalize_observation(action, observation)
        if not observation.done and self._state.step_count >= self.max_episode_steps:
            observation.done = True
            observation.reward = 0.0 if observation.reward is None else observation.reward
            observation.metadata = {
                **getattr(observation, "metadata", {}),
                "truncated": True,
                "max_episode_steps": self.max_episode_steps,
            }
        self._terminated = bool(observation.done)
        self.trajectory_logger.log_step(
            episode_id=str(self._state.episode_id),
            step_index=int(self._state.step_count),
            action=action,
            observation=observation,
            state=self._state_dict(),
        )
        return observation

    def _coerce_mcp_action(self, action: Action) -> Action:
        """Convert web-form actions into concrete MCP action models."""
        if isinstance(action, MCPWebAction):
            if action.type == "list_tools":
                return ListToolsAction(metadata=action.metadata)
            return CallToolAction(
                metadata=action.metadata,
                tool_name=action.tool_name or "",
                arguments=action.arguments,
            )
        return action

    @property
    def state(self) -> State:
        return self._state

    @property
    def trajectory_path(self) -> Path | None:
        return self.trajectory_logger.current_path

    def _normalize_observation(self, action: Action, observation: Observation) -> Observation:
        if observation.reward is None:
            observation.reward = 0.0

        if isinstance(action, CallToolAction) and isinstance(observation, CallToolObservation):
            result = self._extract_tool_result(observation.result)
            if isinstance(result, dict):
                if "reward" in result and result["reward"] is not None:
                    observation.reward = float(result["reward"])
                if "done" in result:
                    observation.done = bool(result["done"])
                if "accepted" in result or "message" in result:
                    observation.metadata = {
                        **getattr(observation, "metadata", {}),
                        "accepted": result.get("accepted"),
                        "message": result.get("message"),
                    }

        if isinstance(action, ListToolsAction) and observation.reward is None:
            observation.reward = 0.0

        return observation

    def _state_dict(self) -> dict[str, Any]:
        if hasattr(self._state, "model_dump"):
            return self._state.model_dump()
        return {
            "episode_id": getattr(self._state, "episode_id", None),
            "step_count": getattr(self._state, "step_count", 0),
        }

    def _extract_tool_result(self, result: Any) -> Any:
        if isinstance(result, dict):
            return result
        for attribute in ("data", "structured_content"):
            candidate = getattr(result, attribute, None)
            if isinstance(candidate, dict):
                return candidate
        return result

    def _require_controller_episode_id(self) -> str:
        if self._controller_episode_id is None:
            raise RuntimeError("Environment has not been reset yet.")
        return self._controller_episode_id
