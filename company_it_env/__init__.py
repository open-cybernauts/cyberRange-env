"""Standalone OpenEnv package for the company IT lab."""

try:
    from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction
except Exception:  # pragma: no cover - dependency resolved in environment runtime
    CallToolAction = object  # type: ignore[assignment]
    ListToolsAction = object  # type: ignore[assignment]

from .client import CompanyITEnv

__all__ = ["CompanyITEnv", "CallToolAction", "ListToolsAction"]
