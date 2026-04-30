# Environment Variables

All runtime configuration is environment-driven with the `SWITCH_` prefix.

## Required Production Values

- `SWITCH_LOCAL_ONLY=true`
- `SWITCH_DATABASE_URL=postgresql+psycopg://...@postgres:5432/switch`
- `SWITCH_REDIS_URL=redis://redis:6379/0`
- `SWITCH_VECTOR_STORE_URL=http://qdrant:6333`
- `SWITCH_VLLM_ENDPOINT=http://model-gateway:8001/v1` or approved local endpoint.
  Use `http://host.docker.internal:11434/v1` for host Ollama from Compose.
- `SWITCH_POSTGRES_PASSWORD`: change the example value before deployment
- `SWITCH_PROTECTED_BRANCHES`: include `main`, `master`, release branches

## Hardening Defaults

- `SWITCH_SANDBOX_NETWORK_ENABLED=false`
- `SWITCH_SANDBOX_CPU_COUNT=1`
- `SWITCH_SANDBOX_MEMORY=1g`
- `SWITCH_SANDBOX_TIMEOUT_SECONDS=60`
- `SWITCH_AUDIT_RETENTION_DAYS=365`
- `SWITCH_DEFAULT_PERMISSION_LEVEL=1`
- `SWITCH_ALLOWED_LOCAL_HOSTS=["localhost","backend","dashboard","postgres","redis","qdrant","model-gateway","host.docker.internal"]`

## Model Roles

- `SWITCH_PLANNER_MODEL`
- `SWITCH_CODER_MODEL`
- `SWITCH_REVIEWER_MODEL`
- `SWITCH_SUMMARIZER_MODEL`
- `SWITCH_EMBEDDING_MODEL`
- `SWITCH_RERANKER_MODEL`

Leave roles blank until a local model is available. Do not add cloud provider API
keys.
