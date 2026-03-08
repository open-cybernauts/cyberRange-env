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

`company_it_env` is a standalone OpenEnv environment package that now acts as a control plane for a remote cyber range.

The Space-facing app exposes OpenEnv tools for scenario briefing, attacker access, episode status, and flag submission. A controller service can run separately and provision the actual attacker and target workloads on infrastructure you control. For local development, the repo still includes a simulated controller backend so the full flow can be exercised without external infrastructure.

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
    ├── cluster_layout.py
    ├── company_it_environment.py
    ├── controller.py
    ├── controller_service.py
    ├── kind_provisioner.py
    ├── solver.py
    ├── web_ui.py
    └── Dockerfile
```

## Local Development

### Space / control plane

```bash
cd company_it_env
pip install -e .
uv lock
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000/web`.

### Standalone controller service

```bash
cd company_it_env
controller-server
```

This starts the controller API on port `8010`.

By default it uses the built-in simulated backend. To make the controller talk to external infrastructure instead, configure:

```bash
export COMPANY_IT_CONTROLLER_BACKEND="provisioner"
export COMPANY_IT_PROVISIONER_URL="https://<your-provisioner-api>"
export COMPANY_IT_PROVISIONER_TOKEN="<optional-bearer-token>"
controller-server
```

## Docker Build

```bash
cd company_it_env
docker build -t company-it-env -f server/Dockerfile .
docker run --rm -p 8000:8000 company-it-env
```

## Remote Controller

Point the Space/control-plane app at an external controller by setting:

```bash
export COMPANY_IT_REMOTE_CONTROLLER_URL="http://127.0.0.1:8010"
```

When this variable is unset, the app falls back to the built-in simulated controller.

When the controller itself is running in `provisioner` mode, the flow becomes:
- Space/OpenEnv app talks to `controller-server`
- `controller-server` performs deterministic scenario selection and flag generation
- `controller-server` calls the external provisioner API to create attacker/target infrastructure
- the agent receives only attacker access and target service details through the control plane

The external provisioner API is expected to expose:
- `GET /health`
- `POST /episodes`
- `GET /episodes/{episode_id}/status`
- `GET /episodes/{episode_id}/attacker-access`
- `DELETE /episodes/{episode_id}`

The `POST /episodes` body is the controller-generated provisioning request containing the selected scenario, seed bundle, and remote cluster layout, and should return attacker access plus episode status.

### Local `kind` backend

If Docker Desktop is enabled and you want the controller to provision a local cluster directly, configure:

```bash
export COMPANY_IT_CONTROLLER_BACKEND="kind"
export COMPANY_IT_KIND_CLUSTER="openenv-range"
export COMPANY_IT_KIND_AUTO_CREATE="true"
controller-server
```

This backend uses `kind` and `kubectl` to:
- create the cluster if needed
- create a per-episode namespace
- deploy a `redteam` pod with bash/network tooling
- deploy in-cluster target services for the helpdesk and internal API flows

The returned attacker access includes a bootstrap command like:

```bash
kubectl --context kind-openenv-range exec -it -n <episode-namespace> deploy/redteam -- bash
```

Once inside the `redteam` pod, the target services are reachable only over cluster networking using the service DNS names returned by `get_attacker_access`.

## Baseline Solver

```bash
cd company_it_env
LAB_EPISODE_ID="<episode-id>" LAB_TARGET_BASE_URL="http://127.0.0.1:8000/simulated-target/<episode-id>" python -m server.solver
```

Or against a remote Space and remote controller-managed target:

```bash
cd company_it_env
LAB_BASE_URL="https://<your-space>.hf.space" LAB_EPISODE_ID="<episode-id>" LAB_TARGET_BASE_URL="https://<target-base-url>" python -m server.solver
```

## Validation

```bash
cd company_it_env
pytest
validate-rl
openenv validate
```

`validate-rl` checks deterministic episode provisioning, controller-backed reward and termination handling, episode truncation, and trajectory replay against the logged JSONL traces under `outputs/evals/trajectories/`.

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

The Space remains intentionally lightweight because Hugging Face Spaces is not a good fit for running a nested Kubernetes cluster with privileged container access. Use the Space as the OpenEnv front end and run the controller and real cluster elsewhere.
