"""Custom tracked web UI for the Company IT OpenEnv Space."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Type

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from openenv.core.env_server.http_server import create_fastapi_app
from openenv.core.env_server.types import Action, EnvironmentMetadata, Observation
from openenv.core.env_server.web_interface import (
    WebInterfaceManager,
    _markdown_to_html,
    load_environment_metadata,
)


def create_company_web_interface_app(
    env,
    action_cls: Type[Action],
    observation_cls: Type[Observation],
    env_name: Optional[str] = None,
    max_concurrent_envs: Optional[int] = None,
    concurrency_config: Optional[Any] = None,
) -> FastAPI:
    """Create a FastAPI app with a tracked custom web interface."""
    app = create_fastapi_app(
        env, action_cls, observation_cls, max_concurrent_envs, concurrency_config
    )

    metadata = load_environment_metadata(env, env_name)
    web_manager = WebInterfaceManager(env, action_cls, observation_cls, metadata)
    field_overrides = _build_action_field_overrides(web_manager.env)

    @app.get("/web", response_class=HTMLResponse)
    async def web_interface():
        return get_company_web_interface_html(
            action_cls, web_manager.metadata, field_overrides
        )

    @app.get("/web/metadata")
    async def web_metadata():
        return web_manager.metadata.model_dump()

    @app.websocket("/ws/ui")
    async def websocket_ui_endpoint(websocket: WebSocket):
        await web_manager.connect_websocket(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await web_manager.disconnect_websocket(websocket)

    @app.post("/web/reset")
    async def web_reset():
        return await web_manager.reset_environment()

    @app.post("/web/step")
    async def web_step(request: Dict[str, Any]):
        action_data = request.get("action", {})
        return await web_manager.step_environment(action_data)

    @app.get("/web/state")
    async def web_state():
        return web_manager.get_state()

    return app


def get_company_web_interface_html(
    action_cls: Type[Action],
    metadata: Optional[EnvironmentMetadata],
    field_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    action_fields = _extract_action_fields(action_cls, field_overrides=field_overrides)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenEnv Web Interface</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            height: 100vh;
            overflow: hidden;
        }}

        .container {{
            display: flex;
            height: 100vh;
        }}

        .left-pane {{
            width: 50%;
            background: white;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
        }}

        .right-pane {{
            width: 50%;
            background: #fafafa;
            display: flex;
            flex-direction: column;
        }}

        .pane-header {{
            padding: 20px;
            border-bottom: 1px solid #e0e0e0;
            background: #f8f9fa;
            font-weight: 600;
            font-size: 16px;
        }}

        .pane-content {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }}

        .action-form, .state-display, .logs-container, .instructions-section {{
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
        }}

        .action-form, .instructions-section {{
            padding: 20px;
            margin-bottom: 20px;
        }}

        .state-display {{
            padding: 15px;
            margin-bottom: 20px;
        }}

        .logs-container {{
            padding: 15px;
            max-height: 400px;
            overflow-y: auto;
        }}

        .form-group {{
            margin-bottom: 15px;
        }}

        .form-group label {{
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #333;
        }}

        .form-group input,
        .form-group textarea,
        .form-group select {{
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            background: white;
        }}

        .form-group input:focus,
        .form-group textarea:focus,
        .form-group select:focus {{
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
        }}

        .form-group textarea {{
            resize: vertical;
            font-family: monospace;
        }}

        .help-text {{
            display: block;
            margin-top: 5px;
            font-size: 12px;
            color: #6c757d;
            font-style: italic;
        }}

        .btn {{
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-right: 10px;
            margin-bottom: 10px;
        }}

        .btn:hover {{
            background: #0056b3;
        }}

        .btn-secondary {{
            background: #6c757d;
        }}

        .btn-secondary:hover {{
            background: #545b62;
        }}

        .state-item {{
            margin-bottom: 8px;
        }}

        .state-label {{
            font-weight: 500;
            color: #666;
        }}

        .state-value {{
            color: #333;
            font-family: monospace;
        }}

        .status-indicator {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
        }}

        .status-connected {{
            background: #28a745;
        }}

        .status-disconnected {{
            background: #dc3545;
        }}

        .json-display {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
        }}

        .log-entry {{
            border-bottom: 1px solid #f0f0f0;
            padding: 10px 0;
        }}

        .log-entry:last-child {{
            border-bottom: none;
        }}

        .log-timestamp {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}

        .log-action {{
            background: #e3f2fd;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 5px;
            font-family: monospace;
            font-size: 12px;
        }}

        .log-observation {{
            background: #f3e5f5;
            padding: 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
        }}

        .log-reward {{
            font-weight: 600;
            color: #28a745;
        }}

        .log-done {{
            font-weight: 600;
            color: #dc3545;
        }}

        .instructions-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}

        .instructions-title {{
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin: 0;
        }}

        .instructions-toggle {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 5px 10px;
            cursor: pointer;
            font-size: 12px;
            color: #6c757d;
        }}

        .instructions-content {{
            display: none;
            max-height: 400px;
            overflow-y: auto;
            border-top: 1px solid #e0e0e0;
            padding-top: 15px;
        }}

        .instructions-content.expanded {{
            display: block;
        }}

        .instructions-content h1,
        .instructions-content h2,
        .instructions-content h3 {{
            color: #333;
            margin-top: 20px;
            margin-bottom: 10px;
        }}

        .instructions-content p {{
            margin-bottom: 10px;
            line-height: 1.6;
        }}

        .instructions-content code {{
            background: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 14px;
        }}

        .instructions-content pre {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            padding: 15px;
            overflow-x: auto;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="left-pane">
            <div class="pane-header">
                <span class="status-indicator status-disconnected" id="connection-status"></span>
                HumanAgent Interface
            </div>
            <div class="pane-content">
                {_generate_instructions_section(metadata)}
                <div class="action-form">
                    <h3>Take Action</h3>
                    <form id="action-form">
                        {_generate_action_form_fields(action_fields)}
                        <button type="submit" class="btn" id="step-btn">Step</button>
                    </form>
                </div>
                <div style="margin-bottom: 20px;">
                    <button class="btn btn-secondary" id="reset-btn">Reset Environment</button>
                    <button class="btn btn-secondary" id="state-btn">Get State</button>
                </div>
                <div class="state-display">
                    <h3>Current State</h3>
                    <div id="current-state">
                        <div class="state-item">
                            <span class="state-label">Status:</span>
                            <span class="state-value" id="env-status">Not initialized</span>
                        </div>
                        <div class="state-item">
                            <span class="state-label">Episode ID:</span>
                            <span class="state-value" id="episode-id">-</span>
                        </div>
                        <div class="state-item">
                            <span class="state-label">Step Count:</span>
                            <span class="state-value" id="step-count">0</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="right-pane">
            <div class="pane-header">State Observer</div>
            <div class="pane-content">
                <div class="state-display">
                    <h3>Current Observation</h3>
                    <div id="current-observation" class="json-display">No observation yet</div>
                </div>
                <div class="logs-container">
                    <h3>Action History</h3>
                    <div id="action-logs">No actions taken yet</div>
                </div>
            </div>
        </div>
    </div>
    <script>
        class OpenEnvWebInterface {{
            constructor() {{
                this.ws = null;
                this.init();
            }}

            init() {{
                this.connectWebSocket();
                this.setupEventListeners();
            }}

            connectWebSocket() {{
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${{protocol}}//${{window.location.host}}/ws/ui`;
                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {{
                    this.updateConnectionStatus(true);
                }};

                this.ws.onmessage = (event) => {{
                    const data = JSON.parse(event.data);
                    if (data.type === 'state_update') {{
                        this.updateUI(data.episode_state);
                    }}
                }};

                this.ws.onclose = () => {{
                    this.updateConnectionStatus(false);
                    setTimeout(() => this.connectWebSocket(), 3000);
                }};
            }}

            setupEventListeners() {{
                const instructionsToggle = document.getElementById('instructions-toggle');
                const instructionsContent = document.getElementById('instructions-content');
                if (instructionsToggle && instructionsContent) {{
                    instructionsToggle.addEventListener('click', () => {{
                        instructionsContent.classList.toggle('expanded');
                        instructionsToggle.textContent = instructionsContent.classList.contains('expanded')
                            ? 'Hide Instructions' : 'Show Instructions';
                    }});
                }}

                const actionForm = document.getElementById('action-form');
                if (actionForm) {{
                    actionForm.addEventListener('submit', (e) => {{
                        e.preventDefault();
                        this.submitAction();
                    }});
                }}
                this.setupActionTypeSwitcher();

                document.getElementById('reset-btn').addEventListener('click', () => {{
                    this.resetEnvironment();
                }});

                document.getElementById('state-btn').addEventListener('click', () => {{
                    this.getState();
                }});
            }}

            setupActionTypeSwitcher() {{
                const typeSelect = document.getElementById('type');
                if (!typeSelect) {{
                    return;
                }}

                const updateFields = () => {{
                    const isListTools = typeSelect.value === 'list_tools';
                    const toolGroup = document.getElementById('tool_name-group');
                    const argumentsGroup = document.getElementById('arguments-group');
                    const toolInput = document.getElementById('tool_name');
                    const argumentsInput = document.getElementById('arguments');

                    if (toolGroup) {{
                        toolGroup.style.display = isListTools ? 'none' : 'block';
                    }}
                    if (argumentsGroup) {{
                        argumentsGroup.style.display = isListTools ? 'none' : 'block';
                    }}
                    if (toolInput) {{
                        toolInput.disabled = isListTools;
                        toolInput.required = !isListTools;
                        if (isListTools) {{
                            toolInput.value = '';
                        }}
                    }}
                    if (argumentsInput) {{
                        argumentsInput.disabled = isListTools;
                        if (isListTools) {{
                            argumentsInput.value = '';
                        }}
                    }}
                }};

                typeSelect.addEventListener('change', updateFields);
                updateFields();
            }}

            async submitAction() {{
                const formData = new FormData(document.getElementById('action-form'));
                const action = {{}};

                for (const [key, value] of formData.entries()) {{
                    if (value === '') {{
                        continue;
                    }}
                    if (key === 'arguments') {{
                        try {{
                            action[key] = JSON.parse(value);
                        }} catch (error) {{
                            alert('Arguments must be valid JSON.');
                            return;
                        }}
                    }} else {{
                        action[key] = value;
                    }}
                }}

                try {{
                    const response = await fetch('/web/step', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ action }})
                    }});

                    if (!response.ok) {{
                        const errorText = await response.text();
                        alert(`Error submitting action: ${{errorText || response.status}}`);
                    }}
                }} catch (error) {{
                    alert(`Error submitting action: ${{error.message}}`);
                }}
            }}

            async resetEnvironment() {{
                const response = await fetch('/web/reset', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});
                if (!response.ok) {{
                    alert('Error resetting environment');
                }}
            }}

            async getState() {{
                const response = await fetch('/web/state');
                const state = await response.json();
                alert('Current state: ' + JSON.stringify(state, null, 2));
            }}

            updateConnectionStatus(connected) {{
                const indicator = document.getElementById('connection-status');
                indicator.className = connected
                    ? 'status-indicator status-connected'
                    : 'status-indicator status-disconnected';
            }}

            updateUI(episodeState) {{
                document.getElementById('env-status').textContent = episodeState.episode_id
                    ? (episodeState.is_reset ? 'Reset' : 'Running')
                    : 'Not initialized';
                document.getElementById('episode-id').textContent =
                    episodeState.episode_id || '-';
                document.getElementById('step-count').textContent =
                    episodeState.step_count.toString();

                const observationDiv = document.getElementById('current-observation');
                observationDiv.textContent = episodeState.current_observation
                    ? JSON.stringify(episodeState.current_observation, null, 2)
                    : 'No observation yet';

                const logsDiv = document.getElementById('action-logs');
                if (episodeState.action_logs.length === 0) {{
                    logsDiv.innerHTML = 'No actions taken yet';
                    return;
                }}

                logsDiv.innerHTML = episodeState.action_logs.map(log => `
                    <div class="log-entry">
                        <div class="log-timestamp">${{log.timestamp}} (Step ${{log.step_count}})</div>
                        <div class="log-action">Action: ${{JSON.stringify(log.action, null, 2)}}</div>
                        <div class="log-observation">Observation: ${{JSON.stringify(log.observation, null, 2)}}</div>
                        <div>
                            <span class="log-reward">Reward: ${{log.reward !== null ? log.reward : 'None'}}</span>
                            ${{log.done ? '<span class="log-done">DONE</span>' : ''}}
                        </div>
                    </div>
                `).join('');
            }}
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            new OpenEnvWebInterface();
        }});
    </script>
</body>
</html>
    """


def _generate_instructions_section(metadata: Optional[EnvironmentMetadata]) -> str:
    if not metadata or not metadata.readme_content:
        return ""

    return f"""
                <div class="instructions-section">
                    <div class="instructions-header">
                        <h3 class="instructions-title">{metadata.name}</h3>
                        <button class="instructions-toggle" id="instructions-toggle">Show Instructions</button>
                    </div>
                    <div class="instructions-content" id="instructions-content">
                        <div class="instructions-readme">
                            {_markdown_to_html(metadata.readme_content)}
                        </div>
                    </div>
                </div>
    """


def _extract_action_fields(
    action_cls: Type[Action],
    field_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    schema = action_cls.model_json_schema()
    properties = schema.get("properties", {})
    required_fields = schema.get("required", [])
    overrides = field_overrides or {}
    action_fields: List[Dict[str, Any]] = []

    for field_name, field_info in properties.items():
        if field_name == "metadata":
            continue

        field_data = {
            "name": field_name,
            "type": _determine_input_type_from_schema(field_info, field_name),
            "required": field_name in required_fields,
            "default_value": field_info.get("default", field_info.get("const")),
            "choices": field_info.get("enum")
            or ([field_info["const"]] if "const" in field_info else None),
            "placeholder": _generate_placeholder(field_name),
            "help_text": _generate_help_text(field_name, field_info.get("description", "")),
        }
        if field_name in overrides:
            field_data.update(overrides[field_name])
        action_fields.append(field_data)

    return action_fields


def _determine_input_type_from_schema(
    field_info: Dict[str, Any], field_name: str
) -> str:
    schema_type = field_info.get("type")
    if "enum" in field_info or "const" in field_info:
        return "select"
    if schema_type == "object" and "arguments" in field_name:
        return "textarea"
    if schema_type == "string":
        return "text"
    return "text"


def _generate_placeholder(field_name: str) -> str:
    if "arguments" in field_name:
        return 'Enter JSON arguments (e.g., {"path": "scenario/k8s/helpdesk-web.yaml"})'
    return f"Enter {field_name.replace('_', ' ')}..."


def _generate_help_text(field_name: str, description: str) -> str:
    if description:
        return description
    if "arguments" in field_name:
        return "JSON object passed to the selected tool. Leave blank for tools with no parameters."
    return ""


def _build_action_field_overrides(env) -> Dict[str, Dict[str, Any]]:
    tool_choices = _extract_mcp_tool_choices(env)
    if not tool_choices:
        return {}

    return {
        "tool_name": {
            "type": "select",
            "choices": tool_choices,
            "help_text": "Select one of the environment's registered MCP tools.",
        }
    }


def _extract_mcp_tool_choices(env) -> List[str]:
    async def _list_tools() -> List[Any]:
        async with env.mcp_client:
            return await env.mcp_client.list_tools()

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            tools = asyncio.run(_list_tools())
        else:
            with ThreadPoolExecutor(max_workers=1) as executor:
                tools = executor.submit(asyncio.run, _list_tools()).result()
    except Exception:
        return []

    return [str(tool.name) for tool in tools if getattr(tool, "name", None)]


def _generate_action_form_fields(action_fields: List[Dict[str, Any]]) -> str:
    return "\n".join(_generate_single_field(field) for field in action_fields)


def _generate_single_field(field: Dict[str, Any]) -> str:
    field_name = field["name"]
    field_type = field["type"]
    required = field["required"]
    placeholder = field.get("placeholder", "")
    help_text = field.get("help_text", "")
    choices = field.get("choices", [])
    default_value = field.get("default_value")

    label_text = field_name.replace("_", " ").title()
    if required:
        label_text += ' <span style="color: red;">*</span>'

    required_attr = "required" if required else ""
    placeholder_attr = f'placeholder="{placeholder}"' if placeholder else ""

    if field_type == "select":
        options_html: List[str] = []
        if not required or (not default_value and len(choices) > 1):
            options_html.append(f'<option value="">-- Select {label_text} --</option>')
        for choice in choices:
            selected = "selected" if str(choice) == str(default_value) else ""
            options_html.append(f'<option value="{choice}" {selected}>{choice}</option>')
        return f"""
            <div class="form-group" id="{field_name}-group">
                <label for="{field_name}">{label_text}:</label>
                <select name="{field_name}" id="{field_name}" {required_attr}>
                    {"".join(options_html)}
                </select>
                {f'<small class="help-text">{help_text}</small>' if help_text else ""}
            </div>
        """

    if field_type == "textarea":
        initial_value = default_value if default_value is not None else ""
        return f"""
            <div class="form-group" id="{field_name}-group">
                <label for="{field_name}">{label_text}:</label>
                <textarea name="{field_name}" id="{field_name}" rows="4" {required_attr} {placeholder_attr}>{initial_value}</textarea>
                {f'<small class="help-text">{help_text}</small>' if help_text else ""}
            </div>
        """

    value_attr = f'value="{default_value}"' if default_value is not None else ""
    return f"""
            <div class="form-group" id="{field_name}-group">
                <label for="{field_name}">{label_text}:</label>
                <input type="text" name="{field_name}" id="{field_name}" {required_attr} {placeholder_attr} {value_attr}>
                {f'<small class="help-text">{help_text}</small>' if help_text else ""}
            </div>
        """
