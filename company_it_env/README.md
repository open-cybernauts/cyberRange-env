---
title: Company IT OpenEnv Lab
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 8000
tags:
  - openenv
  - cybersecurity
  - kubernetes
---

# Company IT OpenEnv Lab

`company_it_env` is a standalone OpenEnv environment package that simulates a small-company IT stack inside a single Hugging Face Docker Space.

The intended deployment is described by realistic Kubernetes manifests under `scenario/k8s/`. Those manifests seed the challenge database using `scenario/sql/init.sql`, but the runtime stays Space-friendly by simulating the stack inside one container.

## Challenge

- Theme: internal employee helpdesk portal
- Attack path: easy application exploit chain
- Goal: recover the database flag and submit it

The public challenge surface is the helpdesk application at `/helpdesk`.

## Package Layout

```text
company_it_env/
├── README.md
├── __init__.py
├── client.py
├── models.py
├── openenv.yaml
├── pyproject.toml
├── scenario/
│   ├── k8s/
│   └── sql/
└── server/
    ├── app.py
    ├── company_it_environment.py
    ├── lab_runtime.py
    ├── solver.py
    └── Dockerfile
```

## Local Development

```bash
cd company_it_env
pip install -e .
uv lock
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000/helpdesk`.

## Docker Build

```bash
cd company_it_env
docker build -t company-it-env -f server/Dockerfile .
docker run --rm -p 8000:8000 company-it-env
```

## Baseline Solver

```bash
cd company_it_env
python -m server.solver
```

Or against a remote Space:

```bash
cd company_it_env
LAB_BASE_URL="https://<your-space>.hf.space" python -m server.solver
```

## Validation

```bash
cd company_it_env
pytest
validate-rl
openenv validate
```

`validate-rl` checks deterministic reset behavior, reward and termination handling,
episode truncation, and trajectory replay against the logged JSONL traces under
`outputs/evals/trajectories/`.

## OpenEnv Usage

```python
from company_it_env import CompanyITEnv

with CompanyITEnv(base_url="http://127.0.0.1:8000") as env:
    env.reset()
    brief = env.call_tool("challenge_brief")
    print(brief["objective"])
```

## Hugging Face Spaces

This package is designed to be pushed as a standalone OpenEnv environment. From inside `company_it_env/`:

```bash
openenv push
```

The runtime is intentionally single-container because Hugging Face Spaces is not a good fit for running a nested Kubernetes cluster with privileged container access. The manifests remain part of the scenario and drive the seeded database state.
