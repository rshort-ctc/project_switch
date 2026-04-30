import * as vscode from "vscode";

import type { ExtensionState } from "./state";
import type { ApprovalRequest, Repository, Task } from "./types";

export class RepositoryTreeProvider implements vscode.TreeDataProvider<RepositoryItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly state: ExtensionState) {
    this.state.onRefresh(() => this.changed.fire());
  }

  getTreeItem(element: RepositoryItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<RepositoryItem[]> {
    try {
      const selectedId = this.state.config.selectedRepositoryId;
      const repos = await this.state.client.listRepositories();
      return repos.map((repo) => new RepositoryItem(repo, repo.id === selectedId));
    } catch (error) {
      return [RepositoryItem.error(error)];
    }
  }
}

export class TaskTreeProvider implements vscode.TreeDataProvider<TaskItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly state: ExtensionState) {
    this.state.onRefresh(() => this.changed.fire());
  }

  getTreeItem(element: TaskItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<TaskItem[]> {
    try {
      const tasks = await this.state.client.listTasks();
      return tasks.map((task) => new TaskItem(task));
    } catch (error) {
      return [TaskItem.error(error)];
    }
  }
}

export class ApprovalTreeProvider implements vscode.TreeDataProvider<ApprovalItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly state: ExtensionState) {
    this.state.onRefresh(() => this.changed.fire());
  }

  getTreeItem(element: ApprovalItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<ApprovalItem[]> {
    try {
      const approvals = await this.state.client.pendingApprovals();
      return approvals.map((approval) => new ApprovalItem(approval));
    } catch (error) {
      return [ApprovalItem.error(error)];
    }
  }
}

export class RepositoryItem extends vscode.TreeItem {
  static error(error: unknown): RepositoryItem {
    const item = new RepositoryItem(
      {
        id: "error",
        name: "Backend unavailable",
        local_path: errorMessage(error),
        default_branch: "",
        is_active: false,
        created_at: "",
        updated_at: "",
      },
      false,
    );
    item.contextValue = "switchError";
    item.iconPath = new vscode.ThemeIcon("error");
    return item;
  }

  constructor(
    readonly repository: Repository,
    selected: boolean,
  ) {
    super(repository.name, vscode.TreeItemCollapsibleState.None);
    this.id = repository.id;
    this.description = selected ? "selected" : repository.default_branch;
    this.tooltip = `${repository.local_path}\n${repository.id}`;
    this.contextValue = "switchRepository";
    this.iconPath = new vscode.ThemeIcon(selected ? "check" : "repo");
    this.command = {
      command: "switch.selectRepository",
      title: "Select Repository",
      arguments: [this],
    };
  }
}

export class TaskItem extends vscode.TreeItem {
  static error(error: unknown): TaskItem {
    const item = new TaskItem({
      id: "error",
      repository_id: "",
      created_by_user_id: "",
      title: "Backend unavailable",
      description: errorMessage(error),
      status: "error",
      created_at: "",
      updated_at: "",
    });
    item.contextValue = "switchError";
    item.iconPath = new vscode.ThemeIcon("error");
    return item;
  }

  constructor(readonly task: Task) {
    super(task.title, vscode.TreeItemCollapsibleState.None);
    this.id = task.id;
    this.description = task.status;
    this.tooltip = `${task.description}\n${task.id}`;
    this.contextValue = "switchTask";
    this.iconPath = new vscode.ThemeIcon(taskIcon(task.status));
    this.command = {
      command: "switch.openTask",
      title: "Show Task Status",
      arguments: [this],
    };
  }
}

export class ApprovalItem extends vscode.TreeItem {
  static error(error: unknown): ApprovalItem {
    const item = new ApprovalItem({
      id: "error",
      task_id: null,
      agent_run_id: "",
      requested_by_user_id: "",
      decided_by_user_id: null,
      status: "error",
      requested_action: "Backend unavailable",
      risk_level: "unknown",
      reason: errorMessage(error),
      diff_summary: null,
      command: null,
      decision_note: null,
      denial_reason: null,
      decided_at: null,
      created_at: "",
      updated_at: "",
    });
    item.contextValue = "switchError";
    item.iconPath = new vscode.ThemeIcon("error");
    return item;
  }

  constructor(readonly approval: ApprovalRequest) {
    super(approval.requested_action, vscode.TreeItemCollapsibleState.None);
    this.id = approval.id;
    this.description = `${approval.risk_level} risk`;
    this.tooltip = approvalTooltip(approval);
    this.contextValue = "switchApproval";
    this.iconPath = new vscode.ThemeIcon(riskIcon(approval.risk_level));
  }
}

function approvalTooltip(approval: ApprovalRequest): string {
  return [
    `id: ${approval.id}`,
    `status: ${approval.status}`,
    `risk: ${approval.risk_level}`,
    `reason: ${approval.reason}`,
    approval.command ? `command: ${approval.command}` : "",
    approval.diff_summary ? `diff: ${approval.diff_summary}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function taskIcon(status: string): string {
  switch (status.toLowerCase()) {
    case "completed":
      return "pass";
    case "failed":
    case "cancelled":
      return "error";
    case "running":
      return "sync~spin";
    default:
      return "circle-outline";
  }
}

function riskIcon(risk: string): string {
  switch (risk.toLowerCase()) {
    case "high":
    case "critical":
      return "warning";
    case "medium":
      return "shield";
    default:
      return "info";
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
