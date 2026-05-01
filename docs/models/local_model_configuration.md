# Local Model Configuration

SWITCH expects a local vLLM OpenAI-compatible endpoint. The default is:

```bash
SWITCH_VLLM_ENDPOINT=http://localhost:8001/v1
```

In Compose, the backend uses:

```bash
SWITCH_VLLM_ENDPOINT=http://model-gateway:8001/v1
```

If you already run Ollama on the host, use its OpenAI-compatible endpoint from
Compose:

```bash
SWITCH_OLLAMA_ENDPOINT=http://host.docker.internal:11434/v1
```

The Ollama service must listen on an address reachable from Docker containers.
If `ss -ltnp | grep 11434` shows `127.0.0.1:11434`, containers cannot reach it.
For a systemd-managed Ollama install, add a drop-in:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' \
  | sudo tee /etc/systemd/system/ollama.service.d/10-listen.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Only expose that listener on trusted local networks. Use host firewall rules if
the machine is on an untrusted LAN.

`SWITCH_LOCAL_ONLY=true` rejects public vLLM and Ollama endpoints. Configure
model roles with `SWITCH_PLANNER_MODEL`, `SWITCH_CODER_MODEL`,
`SWITCH_REVIEWER_MODEL`, `SWITCH_SUMMARIZER_MODEL`, `SWITCH_EMBEDDING_MODEL`,
and `SWITCH_RERANKER_MODEL`.

For Ollama, use local model names from `ollama list`, for example:

```bash
SWITCH_CODER_MODEL=qwen2.5-coder:7b
SWITCH_PLANNER_MODEL=qwen3.6:latest
SWITCH_REVIEWER_MODEL=qwen3.6:latest
SWITCH_SUMMARIZER_MODEL=llama3.1:8b
SWITCH_EMBEDDING_MODEL=nomic-embed-text:latest
```

Do not use Ollama entries ending in `:cloud` for SWITCH operational deployments
because those delegate inference outside the local machine.

The chat UI can override the configured role model per request. It discovers
available model IDs from `/model-gateway/catalog`. The provider selector routes
vLLM requests through `SWITCH_VLLM_ENDPOINT` and Ollama requests through
`SWITCH_OLLAMA_ENDPOINT`. Remote model options must remain disabled for
operational use because prompts, evidence, and repository context must stay
inside approved local boundaries.

Troubleshooting:

- `/agent/models` shows configured role names.
- `/model-gateway/health` requires a running local model server.
- `/model-gateway/catalog` lists providers and live model IDs when the model
  server is reachable.
- Changing embedding models requires reindexing affected repositories.
