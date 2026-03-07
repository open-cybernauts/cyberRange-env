"""Client wrapper for the company IT OpenEnv lab."""

try:
    from openenv.core.mcp_client import MCPToolClient
except Exception:  # pragma: no cover - dependency resolved in environment runtime
    class MCPToolClient:  # type: ignore[no-redef]
        """Fallback stub used only when OpenEnv is not installed."""

        pass


class CompanyITEnv(MCPToolClient):
    """Thin MCP client for the company IT environment."""

    pass
