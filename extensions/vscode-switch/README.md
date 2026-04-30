# SWITCH Local Agent Extension

VS Code and Cursor client for the local SWITCH coding-agent backend.

The extension is intentionally a thin REST client. It does not run an agent loop, execute shell commands, call cloud APIs, or write patches directly from the editor. Mutating actions go through the local backend approval and audit APIs.

## Development

```bash
npm install
npm run compile
npm test
```

Configure:

- `switch.apiUrl`: local backend URL, default `http://127.0.0.1:8000`
- `switch.localUserId`: existing SWITCH user id for task creation and approval decisions
- `switch.selectedRepositoryId`: selected registered repo id

Use `SWITCH: Connect to Backend` to verify the backend and LOCAL_ONLY state.
