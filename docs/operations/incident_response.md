# Incident Response

## Suspected Secret Exposure

1. Stop the affected task.
2. Deny pending approvals related to the task.
3. Review audit events and tool calls.
4. Rotate the exposed secret outside SWITCH.
5. Reindex after removing secret material.

## Model Server Unavailable

1. Check `/model-gateway/health`.
2. Verify `SWITCH_VLLM_ENDPOINT`.
3. Confirm the vLLM server exposes `/v1/models`.
4. Restart the local model service.

## Sandbox Failure

1. Verify Docker/Podman is installed.
2. Confirm sandbox network is disabled unless explicitly approved.
3. Inspect validation output artifacts.
4. Re-run with the same allowlisted command.
