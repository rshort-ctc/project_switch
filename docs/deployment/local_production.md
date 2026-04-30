# Local Production Deployment

This deployment is designed for an internal network where source code and model
traffic remain local.

## Prerequisites

- Docker Compose or Podman Compose
- Local repository checkout
- Local vLLM-compatible model server or local model files for the optional
  `model` compose profile
- No cloud LLM API keys in the environment

## First Start

```bash
cp .env.example .env
mkdir -p workspaces models backups
docker compose up --build -d postgres redis qdrant migrate backend dashboard
docker compose ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/details
```

The model container is optional because local GPU/runtime requirements vary:

```bash
docker compose --profile model up -d model-gateway
```

If you run vLLM outside Compose, set `SWITCH_VLLM_ENDPOINT` to a localhost or
approved LAN endpoint.

## Service Separation

- `backend`: FastAPI API, policy, audit, repository state, model gateway client
- `dashboard`: Next.js internal dashboard, backend API only
- `postgres`: durable users, repos, tasks, runs, approvals, audit, policy records
- `redis`: local queue/cache service
- `qdrant`: local vector search store
- `model-gateway`: optional vLLM OpenAI-compatible endpoint
- sandbox runtime: Docker or Podman on the host, network disabled by default

## Fresh Deployment Smoke

```bash
docker compose ps
curl http://127.0.0.1:8000/version
curl http://127.0.0.1:8000/agent/models
curl http://127.0.0.1:3000/
scripts/eval --json
```

Do not treat `/model-gateway/health` as required unless a local model server is
running and configured.

## Known Limitations

- Authentication and role management are not production-complete.
- The dashboard exposes approval actions to users with network access to it.
- The model container profile is a template; GPU/device settings are site-specific.
- Compose log rotation controls container logs, not external SIEM retention.
