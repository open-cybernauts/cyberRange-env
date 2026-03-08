"""FastAPI app for the company IT OpenEnv control plane."""

from __future__ import annotations

import os
from html import escape

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from company_it_env.models import EpisodeFlagSubmission, SearchResponse, TicketRecord
from company_it_env.server.company_it_environment import CompanyITEnvironment, MCPWebAction
from company_it_env.server.controller import HttpLabControllerClient, LabController, SimulatedLabController
from company_it_env.server.web_ui import create_company_web_interface_app

try:
    from openenv.core.env_server.mcp_types import CallToolObservation
except Exception:  # pragma: no cover - dependency resolved in environment runtime
    CallToolObservation = object  # type: ignore[assignment]


def render_helpdesk_page(result: SearchResponse | None = None) -> str:
    query = result.query if result else ""
    rows = result.rows if result else []
    error = result.error if result else None

    table_rows = "".join(
        (
            "<tr>"
            f"<td>{row.id}</td>"
            f"<td>{escape(row.title)}</td>"
            f"<td>{escape(row.description)}</td>"
            f"<td>{escape(row.status)}</td>"
            "</tr>"
        )
        for row in rows
    )

    if not table_rows:
        table_rows = (
            "<tr><td colspan='4'>No matching tickets found. "
            "Try searching for `vpn`, `backup`, or `printer`.</td></tr>"
        )

    error_html = (
        f"<div class='error'>Search failed: {escape(error)}</div>"
        if error
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Northbridge Support Portal</title>
    <style>
      body {{
        font-family: Arial, sans-serif;
        background: #0f172a;
        color: #e2e8f0;
        margin: 0;
        padding: 0;
      }}
      header {{
        background: #111827;
        padding: 24px 32px;
        border-bottom: 1px solid #334155;
      }}
      main {{
        max-width: 980px;
        margin: 0 auto;
        padding: 24px 32px 48px;
      }}
      .card {{
        background: #111827;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
      }}
      form {{
        display: flex;
        gap: 12px;
        margin-top: 16px;
      }}
      input[type="text"] {{
        flex: 1;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #475569;
        background: #020617;
        color: #e2e8f0;
      }}
      button {{
        padding: 12px 18px;
        background: #2563eb;
        border: 0;
        border-radius: 8px;
        color: white;
        cursor: pointer;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th, td {{
        padding: 10px 12px;
        border-bottom: 1px solid #1e293b;
        text-align: left;
      }}
      .meta {{
        color: #94a3b8;
        font-size: 0.95rem;
      }}
      .error {{
        margin: 12px 0;
        padding: 10px 12px;
        background: #7f1d1d;
        border-radius: 8px;
      }}
      code {{
        color: #93c5fd;
      }}
      a {{
        color: #93c5fd;
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>Northbridge Support Portal</h1>
      <p class="meta">
        Public helpdesk front end for the Northbridge internal ops platform.
        Search is proxied to the ticket service used by support staff.
      </p>
    </header>
    <main>
      <section class="card">
        <h2>Ticket Search</h2>
        <p class="meta">
          Search open tickets by title. Internal API endpoint:
          <code>/helpdesk/api/search</code>
        </p>
        <form action="/helpdesk" method="get">
          <input
            name="query"
            type="text"
            value="{escape(query)}"
            placeholder="vpn"
          />
          <button type="submit">Search</button>
        </form>
        {error_html}
      </section>
      <section class="card">
        <h2>Results</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Description</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </section>
      <section class="card">
        <h2>Scenario Artifacts</h2>
        <p class="meta">
          Intended deployment manifests are available under <code>/artifacts</code>.
          The runtime here simulates that infrastructure inside a single Space.
        </p>
      </section>
    </main>
  </body>
</html>
"""


def build_controller_from_env() -> LabController:
    remote_url = os.environ.get("COMPANY_IT_REMOTE_CONTROLLER_URL")
    if remote_url:
        return HttpLabControllerClient(remote_url)
    return SimulatedLabController()


def build_app(controller: LabController | None = None) -> FastAPI:
    controller_instance = controller or build_controller_from_env()

    def env_factory() -> CompanyITEnvironment:
        return CompanyITEnvironment(controller=controller_instance)

    if CallToolObservation is not object:
        app = create_company_web_interface_app(
            env_factory,
            MCPWebAction,
            CallToolObservation,
            env_name="company_it_env",
        )
    else:  # pragma: no cover - local import fallback
        app = FastAPI(title="company_it_env")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/web")

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        return JSONResponse(controller_instance.health().model_dump())

    @app.get("/controller/health")
    def controller_health() -> JSONResponse:
        return JSONResponse(controller_instance.health().model_dump())

    @app.get("/scenarios")
    def scenarios() -> JSONResponse:
        return JSONResponse(controller_instance.list_scenarios())

    @app.get("/episodes/{episode_id}/status")
    def episode_status(episode_id: str) -> JSONResponse:
        try:
            payload = controller_instance.get_status(episode_id).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(payload)

    @app.get("/episodes/{episode_id}/attacker-access")
    def episode_attacker_access(episode_id: str) -> JSONResponse:
        try:
            payload = controller_instance.get_attacker_access(episode_id).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(payload)

    @app.post("/challenge/submit")
    def challenge_submit(submission: EpisodeFlagSubmission) -> JSONResponse:
        try:
            result = controller_instance.submit_flag(submission.episode_id, submission.flag)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Episode not found") from exc
        return JSONResponse(result.model_dump())

    if isinstance(controller_instance, SimulatedLabController):

        @app.get("/simulated-target/{episode_id}/helpdesk", response_class=HTMLResponse, include_in_schema=False)
        def helpdesk(episode_id: str, query: str = Query(default="")) -> HTMLResponse:
            try:
                result = (
                    controller_instance.search_public_tickets(episode_id, query)
                    if query
                    else SearchResponse(query="")
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc
            return HTMLResponse(render_helpdesk_page(result))

        @app.get("/simulated-target/{episode_id}/helpdesk/api/search", response_model=SearchResponse)
        def helpdesk_api_search(episode_id: str, query: str = Query(default="")) -> SearchResponse:
            try:
                return controller_instance.search_public_tickets(episode_id, query)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc

        @app.get("/simulated-target/{episode_id}/helpdesk/api/tickets/{ticket_id}", response_model=TicketRecord)
        def helpdesk_api_ticket(episode_id: str, ticket_id: int) -> TicketRecord:
            try:
                ticket = controller_instance.get_public_ticket(episode_id, ticket_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc
            if ticket is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
            return ticket

        @app.get("/simulated-target/{episode_id}/internal-api/v1/status")
        def internal_status(episode_id: str) -> JSONResponse:
            try:
                payload = controller_instance.get_debug_status(episode_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return JSONResponse(payload)

        @app.get("/simulated-target/{episode_id}/ops/artifacts")
        def ops_artifacts(episode_id: str) -> JSONResponse:
            try:
                payload = controller_instance.list_review_artifacts(episode_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return JSONResponse({"artifacts": payload})

        @app.get("/simulated-target/{episode_id}/ops/artifacts/{artifact_path:path}", response_class=PlainTextResponse)
        def ops_artifact(episode_id: str, artifact_path: str) -> PlainTextResponse:
            try:
                contents = controller_instance.read_review_artifact(episode_id, artifact_path)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Episode not found") from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return PlainTextResponse(contents)

    return app


app = build_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
