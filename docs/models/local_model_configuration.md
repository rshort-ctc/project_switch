# Local Model Configuration

SWITCH expects a local vLLM OpenAI-compatible endpoint. The default is:

```bash
SWITCH_VLLM_ENDPOINT=http://localhost:8001/v1
```

In Compose, the backend uses:

```bash
SWITCH_VLLM_ENDPOINT=http://model-gateway:8001/v1
```

`SWITCH_LOCAL_ONLY=true` rejects public model endpoints. Configure model roles
with `SWITCH_PLANNER_MODEL`, `SWITCH_CODER_MODEL`, `SWITCH_REVIEWER_MODEL`,
`SWITCH_SUMMARIZER_MODEL`, `SWITCH_EMBEDDING_MODEL`, and `SWITCH_RERANKER_MODEL`.

Troubleshooting:

- `/agent/models` shows configured role names.
- `/model-gateway/health` requires a running local model server.
- Changing embedding models requires reindexing affected repositories.
