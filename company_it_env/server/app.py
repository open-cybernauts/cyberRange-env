"""FastAPI app for the company IT OpenEnv lab and public helpdesk surface."""

from __future__ import annotations

from html import escape

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from company_it_env.models import FlagSubmission, SearchResponse, TicketRecord
from company_it_env.server.company_it_environment import CompanyITEnvironment
from company_it_env.server.lab_runtime import LabRuntime

try:
    from openenv.core.env_server.http_server import create_app
    from openenv.core.env_server.mcp_types import CallToolAction, CallToolObservation
except Exception:  # pragma: no cover - dependency resolved in environment runtime
    create_app = None  # type: ignore[assignment]
    CallToolAction = object  # type: ignore[assignment]
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


def build_app(runtime: LabRuntime | None = None) -> FastAPI:
    runtime_instance = runtime or LabRuntime()
    runtime_instance.reset()

    def env_factory() -> CompanyITEnvironment:
        return CompanyITEnvironment(runtime=runtime_instance)

    if create_app is not None:
        app = create_app(
            env_factory,
            CallToolAction,
            CallToolObservation,
            env_name="company_it_env",
        )
    else:  # pragma: no cover - local import fallback
        app = FastAPI(title="company_it_env")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/helpdesk")

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        return JSONResponse(runtime_instance.health())

    @app.get("/helpdesk", response_class=HTMLResponse, include_in_schema=False)
    def helpdesk(query: str = Query(default="")) -> HTMLResponse:
        result = runtime_instance.search_tickets(query) if query else SearchResponse(query="")
        return HTMLResponse(render_helpdesk_page(result))

    @app.get("/helpdesk/api/search", response_model=SearchResponse)
    def helpdesk_api_search(query: str = Query(default="")) -> SearchResponse:
        return runtime_instance.search_tickets(query)

    @app.get("/helpdesk/api/tickets/{ticket_id}", response_model=TicketRecord)
    def helpdesk_api_ticket(ticket_id: int) -> TicketRecord:
        ticket = runtime_instance.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    @app.get("/internal-api/v1/status")
    def internal_status() -> JSONResponse:
        return JSONResponse(runtime_instance.internal_status())

    @app.get("/artifacts")
    def artifacts() -> JSONResponse:
        return JSONResponse({"artifacts": runtime_instance.list_artifacts()})

    @app.get("/artifacts/{artifact_path:path}", response_class=PlainTextResponse)
    def artifact(artifact_path: str) -> PlainTextResponse:
        try:
            contents = runtime_instance.read_artifact(artifact_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        return PlainTextResponse(contents)

    @app.post("/challenge/submit")
    def challenge_submit(submission: FlagSubmission) -> JSONResponse:
        return JSONResponse(runtime_instance.submit_flag(submission.flag).model_dump())

    return app


app = build_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
