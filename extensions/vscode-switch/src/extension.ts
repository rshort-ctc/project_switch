import * as vscode from "vscode";

import { registerCommands } from "./commands";
import { ExtensionState } from "./state";
import { ApprovalTreeProvider, RepositoryTreeProvider, TaskTreeProvider } from "./tree";

export function activate(context: vscode.ExtensionContext): void {
  const state = new ExtensionState();
  context.subscriptions.push(state);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      "switch.repositories",
      new RepositoryTreeProvider(state),
    ),
    vscode.window.registerTreeDataProvider("switch.tasks", new TaskTreeProvider(state)),
    vscode.window.registerTreeDataProvider("switch.approvals", new ApprovalTreeProvider(state)),
  );

  registerCommands(context, state);
}

export function deactivate(): void {
  // No long-running resources are owned by the extension.
}
