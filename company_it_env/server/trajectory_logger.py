"""Helpers for persisting environment trajectories as JSONL."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    for attribute in ("data", "structured_content"):
        candidate = getattr(value, attribute, None)
        if isinstance(candidate, dict):
            return _json_safe(candidate)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


class TrajectoryLogger:
    """Writes reset and step events to per-episode JSONL files."""

    def __init__(self, output_root: Path) -> None:
        self.output_dir = output_root / "evals" / "trajectories"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._current_episode_id: str | None = None
        self._current_path: Path | None = None

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def start_episode(
        self,
        *,
        episode_id: str,
        seed: int | None,
        observation: Any,
        state: dict[str, Any],
    ) -> Path:
        path = self.output_dir / f"{episode_id}.jsonl"
        self._current_episode_id = episode_id
        self._current_path = path
        self._append(
            {
                "trajectory_version": 1,
                "event": "reset",
                "timestamp": self._timestamp(),
                "episode_id": episode_id,
                "seed": seed,
                "state": _json_safe(state),
                "observation": _json_safe(observation),
            }
        )
        return path

    def log_step(
        self,
        *,
        episode_id: str,
        step_index: int,
        action: Any,
        observation: Any,
        state: dict[str, Any],
    ) -> None:
        self._append(
            {
                "trajectory_version": 1,
                "event": "step",
                "timestamp": self._timestamp(),
                "episode_id": episode_id,
                "step_index": step_index,
                "state": _json_safe(state),
                "action": _json_safe(action),
                "observation": _json_safe(observation),
            }
        )

    def _append(self, payload: dict[str, Any]) -> None:
        if self._current_path is None:
            raise RuntimeError("Trajectory logging started before reset")
        with self._lock:
            with self._current_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()
