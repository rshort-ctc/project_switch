# VS Code and Cursor Extension

The SWITCH extension lives in `extensions/vscode-switch` and works in VS Code-compatible editors, including Cursor. It is a local REST client for the backend.

## Security Model

- The extension does not call cloud APIs.
- The extension does not run shell commands.
- The extension does not implement agent planning, patching, retrieval, validation, or approval logic.
- All task creation, retrieval, diff review, approval, and denial actions go through the local backend API.
- `switch.apiUrl` is restricted to local, `.local`, or `.internal` hosts before requests are made.
- Patch application is available only through the backend `apply-approved-patch` API after an `apply_patch` approval is approved. The extension never writes files directly.

## Setup

1. Start the local backend.
2. Open this repository in VS Code or Cursor.
3. Open `extensions/vscode-switch`.
4. Run:

```bash
npm install
npm run compile
```

Then launch the extension host from the editor.

## Configuration

- `switch.apiUrl`: local backend URL, default `http://127.0.0.1:55600`.
- `switch.localUserId`: existing backend user id for task creation and approvals.
- `switch.selectedRepositoryId`: selected registered repository id.
- `switch.defaultBranch`: branch recorded when registering a workspace.
- `switch.maxAskBundles`: maximum retrieved citations shown for ask results.

## Commands

- `SWITCH: Connect to Backend`
- `SWITCH: Register Current Workspace`
- `SWITCH: Select Registered Repo`
- `SWITCH: Index Selected Repo`
- `SWITCH: Ask Repo Question`
- `SWITCH: Create Coding Task from Selection`
- `SWITCH: Create Coding Task from Current File`
- `SWITCH: Show Task Status`
- `SWITCH: Show Proposed Diff`
- `SWITCH: Apply Approved Patch`
- `SWITCH: Approve Action`
- `SWITCH: Deny Action`

## Views

The SWITCH activity bar container exposes:

- Repositories
- Tasks
- Approvals

All views refresh from backend state. Mutating actions are approval decisions or task creation requests sent to the backend; they do not bypass policy or audit logging.

## Validation

From `extensions/vscode-switch`:

```bash
npm run check
npm test
```
