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
scripts/switch start
docker compose ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/details
```

The model container is optional because local GPU/runtime requirements vary:

```bash
docker compose --profile model up -d switch-vllm
```

If you run vLLM outside Compose, set `SWITCH_VLLM_ENDPOINT` to a localhost or
approved LAN endpoint.

## Service Separation

- `switch-api`: FastAPI API, policy, audit, repository state, model gateway client
- `switch-dashboard`: host-only Next.js dashboard on `127.0.0.1:3000` for metrics, diagnostics, approvals, and audit review
- `switch-web`: limited Next.js network web surface on `0.0.0.0:3001` by default, chat and repository views only
- `switch-db`: durable users, repos, tasks, runs, approvals, audit, policy records
- `switch-redis`: local queue/cache service
- `switch-qdrant`: local vector search store
- `switch-vllm`: optional vLLM OpenAI-compatible endpoint
- sandbox runtime: Docker or Podman on the host, network disabled by default

## Fresh Deployment Smoke

```bash
docker compose ps
curl http://127.0.0.1:8000/version
curl http://127.0.0.1:8000/agent/models
curl http://127.0.0.1:3000/chat
curl http://127.0.0.1:3001/chat
scripts/eval --json
```

Do not treat `/model-gateway/health` as required unless a local model server is
running and configured.

## Known Limitations

- Authentication and role management should be completed before exposing privileged host-only workflows beyond the host machine.
- The model container profile is a template; GPU/device settings are site-specific.
- Compose log rotation controls container logs, not external SIEM retention.
