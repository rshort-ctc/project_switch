import * as vscode from "vscode";

import { setSelectedRepository } from "./config";
import { showDiffDocument, showMarkdown, openWorkspaceFile } from "./documents";
import {
  renderApprovalMarkdown,
  renderAskMarkdown,
  renderHealthMarkdown,
  renderTaskMarkdown,
  sanitizeTitle,
} from "./render";
import type { ExtensionState } from "./state";
import { ApprovalItem, RepositoryItem, TaskItem } from "./tree";
import type { ApprovalRequest, Repository, Task } from "./types";

export function registerCommands(context: vscode.ExtensionContext, state: ExtensionState): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("switch.connect", () => connect(state)),
    vscode.commands.registerCommand("switch.refresh", () => state.refresh()),
    vscode.commands.registerCommand("switch.registerWorkspace", () => registerWorkspace(state)),
    vscode.commands.registerCommand("switch.selectRepository", (item?: RepositoryItem) =>
      selectRepository(state, item?.repository),
    ),
    vscode.commands.registerCommand("switch.indexRepository", () => indexRepository(state)),
    vscode.commands.registerCommand("switch.askRepo", () => askRepo(state)),
    vscode.commands.registerCommand("switch.createTaskFromSelection", () =>
      createTaskFromEditor(state, "selection"),
    ),
    vscode.commands.registerCommand("switch.createTaskFromFile", () =>
      createTaskFromEditor(state, "file"),
    ),
    vscode.commands.registerCommand("switch.openTask", (item?: TaskItem) =>
      openTask(state, item?.task),
    ),
    vscode.commands.registerCommand("switch.openTaskDiff", (item?: TaskItem) =>
      openTaskDiff(state, item?.task),
    ),
    vscode.commands.registerCommand("switch.applyApprovedPatch", (item?: TaskItem) =>
      applyApprovedPatch(state, item?.task),
    ),
    vscode.commands.registerCommand("switch.openRetrievedFile", (contextIndex?: number) =>
      openRetrievedFile(state, contextIndex),
    ),
    vscode.commands.registerCommand("switch.approve", (item?: ApprovalItem) =>
      decideApproval(state, "approve", item?.approval),
    ),
    vscode.commands.registerCommand("switch.deny", (item?: ApprovalItem) =>
      decideApproval(state, "deny", item?.approval),
    ),
  );
}

async function connect(state: ExtensionState): Promise<void> {
  await withProgress("Connecting to SWITCH backend", async () => {
    const health = await state.client.health();
    await showMarkdown("SWITCH Backend", renderHealthMarkdown(health));
    vscode.window.showInformationMessage(
      `SWITCH backend ${health.status}; LOCAL_ONLY=${health.local_only}`,
    );
  });
}

async function registerWorkspace(state: ExtensionState): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    vscode.window.showErrorMessage("Open a workspace folder before registering a repository.");
    return;
  }
  const defaultName = folder.name;
  const name = await vscode.window.showInputBox({
    title: "Repository display name",
    value: defaultName,
    ignoreFocusOut: true,
  });
  if (!name) {
    return;
  }
  await withProgress("Registering workspace", async () => {
    const repo = await state.client.addRepository({
      name,
      local_path: folder.uri.fsPath,
      default_branch: state.config.defaultBranch,
    });
    await setSelectedRepository(repo.id);
    state.refresh();
    vscode.window.showInformationMessage(`Registered and selected ${repo.name}`);
  });
}

async function selectRepository(state: ExtensionState, repo?: Repository): Promise<void> {
  const selected = repo ?? (await pickRepository(state));
  if (!selected) {
    return;
  }
  await setSelectedRepository(selected.id);
  state.refresh();
  vscode.window.showInformationMessage(`Selected SWITCH repo ${selected.name}`);
}

async function indexRepository(state: ExtensionState): Promise<void> {
  const repo = await selectedRepository(state);
  if (!repo) {
    return;
  }
  await withProgress(`Indexing ${repo.name}`, async () => {
    const index = await state.client.indexRepository(repo.id);
    state.refresh();
    vscode.window.showInformationMessage(
      `Indexed ${index.indexed_files} files and ${index.indexed_chunks} chunks`,
    );
  });
}

async function askRepo(state: ExtensionState): Promise<void> {
  const repo = await selectedRepository(state);
  if (!repo) {
    return;
  }
  const question = await vscode.window.showInputBox({
    title: `Ask ${repo.name}`,
    prompt: "Question for the local backend retrieval engine",
    ignoreFocusOut: true,
  });
  if (!question) {
    return;
  }
  await withProgress("Retrieving local repo context", async () => {
    const response = await state.client.ask(repo.id, question, state.config.maxAskBundles);
    state.lastContexts = response.contexts;
    await showMarkdown("SWITCH Context", renderAskMarkdown(response));
  });
}

async function createTaskFromEditor(
  state: ExtensionState,
  mode: "selection" | "file",
): Promise<void> {
  const repo = await selectedRepository(state);
  if (!repo) {
    return;
  }
  const userId = await requireUserId(state);
  if (!userId) {
    return;
  }
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage("Open a file before creating a coding task.");
    return;
  }
  const selectionText = editor.document.getText(editor.selection).trim();
  const relativePath = vscode.workspace.asRelativePath(editor.document.uri, false);
  const sourceText = mode === "selection" && selectionText ? selectionText : relativePath;
  const title = await vscode.window.showInputBox({
    title: "Coding task title",
    value: sanitizeTitle(sourceText) || `Update ${relativePath}`,
    ignoreFocusOut: true,
  });
  if (!title) {
    return;
  }
  const prompt = mode === "selection" ? "Task instructions for selected text" : "Task instructions";
  const instructions = await vscode.window.showInputBox({
    title: prompt,
    prompt: "The backend will handle retrieval, policy, approvals, and audit logging.",
    ignoreFocusOut: true,
  });
  if (!instructions) {
    return;
  }
  const description = [
    instructions,
    "",
    `Source file: ${relativePath}`,
    mode === "selection" && selectionText ? `Selected text:\n${selectionText}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  await withProgress("Creating SWITCH task", async () => {
    const response = await state.client.createTask({
      repository_id: repo.id,
      created_by_user_id: userId,
      title,
      description,
    });
    state.refresh();
    vscode.window.showInformationMessage(
      `Created task ${response.task.id}; run ${response.run?.id ?? "not created"}`,
    );
  });
}

async function openTask(state: ExtensionState, task?: Task): Promise<void> {
  const selected = task ?? (await pickTask(state));
  if (!selected) {
    return;
  }
  await withProgress("Loading task status", async () => {
    const [status, diff, validations, logs] = await Promise.all([
      state.client.taskStatus(selected.id),
      state.client.taskDiff(selected.id),
      state.client.taskValidations(selected.id),
      state.client.taskLogs(selected.id),
    ]);
    await showMarkdown("SWITCH Task", renderTaskMarkdown(status, diff, validations, logs));
  });
}

async function openTaskDiff(state: ExtensionState, task?: Task): Promise<void> {
  const selected = task ?? (await pickTask(state));
  if (!selected) {
    return;
  }
  await withProgress("Loading task diff", async () => {
    const diff = await state.client.taskDiff(selected.id);
    await showDiffDocument(diff.diff);
  });
}

async function applyApprovedPatch(state: ExtensionState, task?: Task): Promise<void> {
  const selected = task ?? (await pickTask(state));
  if (!selected) {
    return;
  }
  const userId = await requireUserId(state);
  if (!userId) {
    return;
  }
  const approvalRequestId = await vscode.window.showInputBox({
    title: "Approved apply_patch approval id",
    prompt: "Use an approval id that the backend has already marked approved.",
    ignoreFocusOut: true,
  });
  if (!approvalRequestId) {
    return;
  }
  await applyPatchWithApproval(state, selected, userId, approvalRequestId);
}

async function applyPatchWithApproval(
  state: ExtensionState,
  task: Task,
  userId: string,
  approvalRequestId: string,
): Promise<void> {
  const approved = await vscode.window.showWarningMessage(
    `Apply backend-approved patch for ${task.title}? This calls the backend policy-gated apply endpoint.`,
    { modal: true },
    "Apply",
  );
  if (approved !== "Apply") {
    return;
  }
  await withProgress("Applying approved patch through backend", async () => {
    const diff = await state.client.taskDiff(task.id);
    if (!diff.diff) {
      vscode.window.showErrorMessage("No backend diff is available to apply.");
      return;
    }
    const result = await state.client.applyApprovedPatch({
      taskId: task.id,
      actorUserId: userId,
      approvalRequestId,
      unifiedDiff: diff.diff,
    });
    state.refresh();
    if (!result.success) {
      vscode.window.showErrorMessage(result.error_message ?? "Backend patch apply failed.");
      return;
    }
    vscode.window.showInformationMessage(
      `Applied patch through backend: ${result.changed_files.length} changed file(s).`,
    );
  });
}

async function openRetrievedFile(
  state: ExtensionState,
  contextIndex: number | undefined,
): Promise<void> {
  const repo = await selectedRepository(state);
  if (!repo) {
    return;
  }
  const context =
    typeof contextIndex === "number"
      ? state.lastContexts[contextIndex]
      : await pickRetrievedContext(state);
  if (!context) {
    return;
  }
  await openWorkspaceFile(repo.local_path, context.path, context.start_line);
}

async function decideApproval(
  state: ExtensionState,
  decision: "approve" | "deny",
  approval?: ApprovalRequest,
): Promise<void> {
  const userId = await requireUserId(state);
  if (!userId) {
    return;
  }
  const selected = approval ?? (await pickApproval(state));
  if (!selected) {
    return;
  }
  await showMarkdown("SWITCH Approval", renderApprovalMarkdown(selected));
  const note = await vscode.window.showInputBox({
    title: `${decision === "approve" ? "Approve" : "Deny"} ${selected.requested_action}`,
    prompt: `${selected.risk_level} risk: ${selected.reason}`,
    ignoreFocusOut: true,
  });
  if (note === undefined) {
    return;
  }
  await withProgress(`${decision === "approve" ? "Approving" : "Denying"} action`, async () => {
    const result =
      decision === "approve"
        ? await state.client.approve(selected.id, userId, note || null)
        : await state.client.deny(selected.id, userId, note || null);
    state.refresh();
    vscode.window.showInformationMessage(`${result.requested_action}: ${result.status}`);
    if (
      decision === "approve" &&
      result.requested_action === "apply_patch" &&
      result.task_id !== null
    ) {
      const tasks = await state.client.listTasks();
      const task = tasks.find((candidate) => candidate.id === result.task_id);
      if (task) {
        await applyPatchWithApproval(state, task, userId, result.id);
      }
    }
  });
}

async function selectedRepository(state: ExtensionState): Promise<Repository | undefined> {
  const repos = await state.client.listRepositories();
  const selectedId = state.config.selectedRepositoryId;
  const selected = repos.find((repo) => repo.id === selectedId);
  if (selected) {
    return selected;
  }
  return pickRepository(state, repos);
}

async function pickRepository(
  state: ExtensionState,
  existing?: Repository[],
): Promise<Repository | undefined> {
  const repos = existing ?? (await state.client.listRepositories());
  const picked = await vscode.window.showQuickPick(
    repos.map((repo) => ({
      label: repo.name,
      description: repo.default_branch,
      detail: repo.local_path,
      repo,
    })),
    { title: "Select SWITCH repository" },
  );
  return picked?.repo;
}

async function pickTask(state: ExtensionState): Promise<Task | undefined> {
  const tasks = await state.client.listTasks();
  const picked = await vscode.window.showQuickPick(
    tasks.map((task) => ({
      label: task.title,
      description: task.status,
      detail: task.id,
      task,
    })),
    { title: "Select SWITCH task" },
  );
  return picked?.task;
}

async function pickApproval(state: ExtensionState): Promise<ApprovalRequest | undefined> {
  const approvals = await state.client.pendingApprovals();
  return pickApprovalFromList(approvals);
}

async function pickApprovalFromList(
  approvals: ApprovalRequest[],
): Promise<ApprovalRequest | undefined> {
  const picked = await vscode.window.showQuickPick(
    approvals.map((approval) => ({
      label: approval.requested_action,
      description: `${approval.risk_level} risk`,
      detail: approval.reason,
      approval,
    })),
    { title: "Select pending approval" },
  );
  return picked?.approval;
}

async function pickRetrievedContext(state: ExtensionState) {
  const picked = await vscode.window.showQuickPick(
    state.lastContexts.map((context, index) => ({
      label: `${context.path}:${context.start_line}-${context.end_line}`,
      description: context.score.toFixed(2),
      detail: context.reasons.join("; "),
      index,
    })),
    { title: "Open retrieved file" },
  );
  return picked ? state.lastContexts[picked.index] : undefined;
}

async function requireUserId(state: ExtensionState): Promise<string | undefined> {
  const configured = state.config.localUserId;
  if (configured) {
    return configured;
  }
  vscode.window.showErrorMessage("Set switch.localUserId before creating tasks or approvals.");
  return undefined;
}

async function withProgress<T>(title: string, task: () => Promise<T>): Promise<T | undefined> {
  try {
    return await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title, cancellable: false },
      task,
    );
  } catch (error) {
    vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
    return undefined;
  }
}
