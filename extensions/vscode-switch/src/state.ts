import * as vscode from "vscode";

import { SwitchApiClient } from "./api";
import { getConfig, type ExtensionConfig } from "./config";
import type { AskContext } from "./types";

export class ExtensionState {
  private readonly refreshEmitter = new vscode.EventEmitter<void>();
  readonly onRefresh = this.refreshEmitter.event;
  lastContexts: AskContext[] = [];

  get config(): ExtensionConfig {
    return getConfig();
  }

  get client(): SwitchApiClient {
    return new SwitchApiClient(this.config.apiUrl);
  }

  refresh(): void {
    this.refreshEmitter.fire();
  }

  dispose(): void {
    this.refreshEmitter.dispose();
  }
}
