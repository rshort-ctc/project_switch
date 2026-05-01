"use client";

import {
  Bot,
  Check,
  ChevronDown,
  Clipboard,
  Code2,
  FileText,
  GitBranch,
  Loader2,
  MessageSquarePlus,
  PanelRight,
  Search,
  Send,
  Terminal,
  ShieldAlert,
  Sparkles,
  SquarePen,
  User,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { runDashboardCode, runDashboardTerminal, sendDashboardChatMessage } from "@/app/actions";
import { safeRandomUUID } from "@/lib/safe-random-uuid";
import type { DashboardSurface } from "@/lib/surface";
import type {
  ApprovalRequest,
  AskContext,
  ChatCodeRunResponse,
  ChatMessage,
  ChatResponse,
  ChatTerminalRunResponse,
  HealthDetails,
  ModelCatalog,
  ModelGatewayHealth,
  ModelRoles,
  Repository,
  Task,
} from "@/lib/types";

type ThreadMessage = ChatMessage & {
  id: string;
  contexts?: AskContext[];
  pending?: ChatPendingActivity;
  response?: ChatResponse;
  createdAt: string;
};

type ChatPendingActivity = {
  startedAt: string;
  repositoryName: string | null;
  maxBundles: number;
  provider: string;
  modelRole: string;
  model: string | null;
};

type Thread = {
  id: string;
  title: string;
  repositoryId: string | null;
  messages: ThreadMessage[];
  updatedAt: string;
};

type ChatWorkspaceProps = {
  repositories: Repository[];
  tasks: Task[];
  approvals: ApprovalRequest[];
  health: HealthDetails | null;
  modelCatalog: ModelCatalog | null;
  modelRoles: ModelRoles | null;
  modelGateway: ModelGatewayHealth | null;
  surface: DashboardSurface;
};

const STORAGE_KEY = "switch.chat.threads";
const DEFAULT_PROMPTS = [
  "Explain the architecture and point me to the important files.",
  "Find likely tests for the current task and summarize coverage gaps.",
  "Review the latest diff for risk and validation needs.",
  "Create a step-by-step implementation plan for this repo change.",
];

export function ChatWorkspace({
  repositories,
  tasks,
  approvals,
  health,
  modelCatalog,
  modelRoles,
  modelGateway,
  surface,
}: ChatWorkspaceProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [modelRole, setModelRole] = useState("coder_model");
  const [provider, setProvider] = useState("local_vllm");
  const [model, setModel] = useState("");
  const [maxBundles, setMaxBundles] = useState(6);
  const [showContext, setShowContext] = useState(true);
  const [terminalCommand, setTerminalCommand] = useState("pwd");
  const [terminalHistory, setTerminalHistory] = useState<ChatTerminalRunResponse[]>([]);
  const [terminalError, setTerminalError] = useState<string | null>(null);
  const [consoleCode, setConsoleCode] = useState("print('hello from SWITCH')");
  const [consoleResult, setConsoleResult] = useState<ChatCodeRunResponse | null>(null);
  const [consoleError, setConsoleError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [isPending, startTransition] = useTransition();
  const [isTerminalPending, startTerminalTransition] = useTransition();
  const [isCodePending, startCodeTransition] = useTransition();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loaded = loadThreads();
    const initial = loaded.length > 0 ? loaded : [createThread(null)];
    setThreads(initial);
    setActiveThreadId(initial[0].id);
  }, []);

  useEffect(() => {
    if (threads.length > 0) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
    }
  }, [threads]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [activeThreadId, threads]);

  useEffect(() => {
    if (!threads.some((thread) => thread.messages.some((message) => message.pending))) {
      return;
    }
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [threads]);

  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? threads[0];
  const isHostSurface = surface === "host";
  const selectedRepository = repositories.find((repo) => repo.id === activeThread?.repositoryId) ?? null;
  const visibleSources = useMemo(() => latestSources(activeThread?.messages ?? []), [activeThread]);
  const providerOptions = useMemo(() => {
    const providers = modelCatalog?.providers ?? ["local_vllm", "ollama_local"];
    return providers.filter(
      (candidate) =>
        candidate !== "ollama_cloud" ||
        Boolean(modelCatalog?.allow_ollama_cloud_models && !modelCatalog.local_only),
    );
  }, [modelCatalog]);
  const providerModels = modelCatalog?.models_by_provider[provider] ?? modelCatalog?.models ?? [];

  function updateActiveThread(update: (thread: Thread) => Thread): void {
    setThreads((current) =>
      current.map((thread) => (thread.id === activeThread?.id ? update(thread) : thread)),
    );
  }

  function startNewThread(repositoryId = selectedRepository?.id ?? null): void {
    const thread = createThread(repositoryId);
    setThreads((current) => [thread, ...current]);
    setActiveThreadId(thread.id);
  }

  function send(content: string): void {
    if (!activeThread || content.trim().length === 0 || isPending) {
      return;
    }
    const userMessage: ThreadMessage = {
      id: safeRandomUUID(),
      role: "user",
      content: content.trim(),
      createdAt: new Date().toISOString(),
    };
    const pendingAssistant: ThreadMessage = {
      id: safeRandomUUID(),
      role: "assistant",
      content: "",
      pending: {
        startedAt: new Date().toISOString(),
        repositoryName: selectedRepository?.name ?? null,
        maxBundles,
        provider,
        modelRole,
        model: model.trim().length > 0 ? model.trim() : null,
      },
      createdAt: new Date().toISOString(),
    };
    const nextMessages = [...activeThread.messages, userMessage, pendingAssistant];
    updateActiveThread((thread) => ({
      ...thread,
      title: thread.messages.length === 0 ? content.trim().slice(0, 64) : thread.title,
      messages: nextMessages,
      updatedAt: new Date().toISOString(),
    }));
    setDraft("");

    startTransition(async () => {
      try {
        const response = await sendDashboardChatMessage({
          repositoryId: activeThread.repositoryId,
          messages: nextMessages
            .filter((message) => message.content.length > 0)
            .map(({ role, content }) => ({ role, content })),
          modelRole,
          provider,
          model: model.trim().length > 0 ? model.trim() : null,
          maxBundles,
        });
        updateActiveThread((thread) => ({
          ...thread,
          messages: thread.messages.map((message) =>
            message.id === pendingAssistant.id
              ? {
                  ...message,
                  content: response.answer,
                  contexts: response.contexts,
                  pending: undefined,
                  response,
                }
              : message,
          ),
          updatedAt: new Date().toISOString(),
        }));
      } catch (error) {
        updateActiveThread((thread) => ({
          ...thread,
          messages: thread.messages.map((message) =>
            message.id === pendingAssistant.id
              ? {
                  ...message,
                  content:
                    error instanceof Error
                      ? `Backend chat failed: ${error.message}`
                      : "Backend chat failed.",
                  pending: undefined,
                }
              : message,
          ),
        }));
      }
    });
  }

  function runConsoleCode(): void {
    if (!isHostSurface) {
      return;
    }
    if (consoleCode.trim().length === 0 || isCodePending) {
      return;
    }
    setConsoleError(null);
    setConsoleResult(null);
    startCodeTransition(async () => {
      try {
        const result = await runDashboardCode({
          language: "python",
          code: consoleCode,
          timeout_seconds: 10,
        });
        setConsoleResult(result);
      } catch (error) {
        setConsoleError(error instanceof Error ? error.message : "Code execution failed.");
      }
    });
  }

  function runTerminalCommand(): void {
    if (!isHostSurface || !selectedRepository) {
      return;
    }
    if (terminalCommand.trim().length === 0 || isTerminalPending) {
      return;
    }
    const command = terminalCommand.trim();
    setTerminalError(null);
    startTerminalTransition(async () => {
      try {
        const result = await runDashboardTerminal({
          repository_id: selectedRepository.id,
          command,
          timeout_seconds: 20,
        });
        setTerminalHistory((current) => [result, ...current].slice(0, 8));
      } catch (error) {
        setTerminalError(error instanceof Error ? error.message : "Terminal command failed.");
      }
    });
  }

  function setThreadRepository(repositoryId: string): void {
    updateActiveThread((thread) => ({ ...thread, repositoryId }));
  }

  async function copyMessage(message: ThreadMessage): Promise<void> {
    await navigator.clipboard.writeText(message.content);
    setCopied(message.id);
    window.setTimeout(() => setCopied(null), 1200);
  }

  return (
    <div className="chat-shell">
      <aside className="chat-threads">
        <div className="chat-sidebar-header">
          <button className="icon-button wide" onClick={() => startNewThread()} type="button">
            <MessageSquarePlus size={16} />
            New chat
          </button>
        </div>
        <div className="thread-list">
          {threads.map((thread) => (
            <button
              className={`thread-row ${thread.id === activeThread?.id ? "active" : ""}`}
              key={thread.id}
              onClick={() => setActiveThreadId(thread.id)}
              type="button"
            >
              <SquarePen size={14} />
              <span>{thread.title}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        <div className="chat-topbar">
          <div className="control-row">
            <label className="select-control">
              <GitBranch size={15} />
              <select
                aria-label="Repository"
                onChange={(event) => setThreadRepository(event.target.value)}
                value={selectedRepository?.id ?? ""}
              >
                <option value="">No repo</option>
                {repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
            <label className="select-control">
              <Sparkles size={15} />
              <select
                aria-label="Model role"
                onChange={(event) => setModelRole(event.target.value)}
                value={modelRole}
              >
                {Object.keys(modelRoles ?? { coder_model: null }).map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
            <label className="select-control">
              <Code2 size={15} />
              <select
                aria-label="Model provider"
                onChange={(event) => {
                  setProvider(event.target.value);
                  setModel("");
                }}
                value={provider}
              >
                {providerOptions.map((candidate) => (
                  <option key={candidate} value={candidate}>
                    {candidate}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
            <label className="select-control model-picker">
              <Bot size={15} />
              <input
                aria-label="Model override"
                list="switch-models"
                onChange={(event) => setModel(event.target.value)}
                placeholder={modelRoles?.[modelRole as keyof ModelRoles] ?? "role default"}
                value={model}
              />
              <datalist id="switch-models">
                {providerModels.map((candidate) => (
                  <option key={candidate} value={candidate} />
                ))}
              </datalist>
            </label>
            <label className="select-control compact">
              <Search size={15} />
              <select
                aria-label="Context bundle count"
                onChange={(event) => setMaxBundles(Number(event.target.value))}
                value={maxBundles}
              >
                {[0, 3, 6, 10, 20].map((count) => (
                  <option key={count} value={count}>
                    {count} files
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
          </div>
          <div className="control-row">
            {isHostSurface ? (
              <>
                <span className={`badge ${health?.local_only ? "success" : "danger"}`}>
                  LOCAL_ONLY={String(health?.local_only ?? "unknown")}
                </span>
                <span className={`badge ${modelGateway?.status === "ok" ? "success" : "warning"}`}>
                  model {modelGateway?.status ?? "offline"}
                </span>
                {provider === "ollama_cloud" ? (
                  <span className="badge danger">remote model policy gated</span>
                ) : null}
              </>
            ) : null}
            <button className="icon-button" onClick={() => setShowContext(!showContext)} type="button">
              <PanelRight size={16} />
            </button>
          </div>
        </div>

        <div className="messages" ref={scrollRef}>
          {(activeThread?.messages.length ?? 0) === 0 ? (
            <div className="welcome-panel">
              <Bot size={30} />
              <h1>SWITCH Chat</h1>
              <p>
                {isHostSurface
                  ? "Ask repo questions, plan changes, review risk, inspect retrieved files, and hand off work to audited tasks without leaving the local control plane."
                  : "Ask repo questions and inspect retrieved local context from the network web surface."}
              </p>
              <div className="prompt-grid">
                {DEFAULT_PROMPTS.map((prompt) => (
                  <button key={prompt} onClick={() => send(prompt)} type="button">
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            activeThread?.messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-avatar">
                  {message.role === "user" ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className="message-body">
                  <div className="message-header">
                    <strong>{message.role === "user" ? "You" : "SWITCH"}</strong>
                    {message.response?.degraded ? <span className="badge warning">retrieval only</span> : null}
                    {message.response?.model ? <span className="badge info">{message.response.model}</span> : null}
                    <button className="ghost-button" onClick={() => copyMessage(message)} type="button">
                      {copied === message.id ? <Check size={14} /> : <Clipboard size={14} />}
                    </button>
                  </div>
                  {message.content ? (
                    <RichText content={message.content} />
                  ) : (
                    <PendingActivity activity={message.pending} now={now} />
                  )}
                  {message.contexts && message.contexts.length > 0 ? (
                    <div className="source-pills">
                      {message.contexts.slice(0, 6).map((context) => (
                        <span key={`${context.path}-${context.start_line}`} className="source-pill">
                          <FileText size={12} />
                          {context.path}:{context.start_line}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            ))
          )}
        </div>

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            send(draft);
          }}
        >
          <textarea
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send(draft);
              }
            }}
            placeholder="Message SWITCH. Shift+Enter for a new line."
            value={draft}
          />
          <button aria-label="Send message" disabled={draft.trim().length === 0 || isPending} type="submit">
            {isPending ? <Loader2 size={18} /> : <Send size={18} />}
          </button>
        </form>
      </section>

      {showContext ? (
        <aside className="chat-context">
          {isHostSurface ? (
            <section>
              <h2>Terminal</h2>
              <div className="terminal-panel">
                <form
                  className="terminal-command-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    runTerminalCommand();
                  }}
                >
                  <span className="terminal-prompt">$</span>
                  <input
                    aria-label="Terminal command"
                    disabled={!selectedRepository}
                    onChange={(event) => setTerminalCommand(event.target.value)}
                    spellCheck={false}
                    value={terminalCommand}
                  />
                  <button
                    aria-label="Run terminal command"
                    className="icon-button compact"
                    disabled={
                      !selectedRepository ||
                      terminalCommand.trim().length === 0 ||
                      isTerminalPending
                    }
                    type="submit"
                  >
                    {isTerminalPending ? <Loader2 size={14} /> : <Send size={14} />}
                  </button>
                </form>
                <div className="console-meta">
                  <span>{selectedRepository?.name ?? "No repo selected"}</span>
                  <span>network off</span>
                </div>
                {terminalError ? <pre className="console-output error">{terminalError}</pre> : null}
                {terminalHistory.length > 0 ? (
                  <div className="terminal-history">
                    {terminalHistory.map((result, index) => (
                      <div className="terminal-result" key={`${result.command}-${index}`}>
                        <div className="console-meta">
                          <span className="mono">$ {result.command}</span>
                          <span>
                            exit {result.exit_code ?? "timeout"} · {result.duration_ms}ms
                          </span>
                        </div>
                        {result.stdout ? (
                          <pre className="console-output">{result.stdout}</pre>
                        ) : null}
                        {result.stderr ? (
                          <pre className="console-output error">{result.stderr}</pre>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}
          {isHostSurface ? (
            <section>
              <h2>Console</h2>
              <div className="console-panel">
                <div className="console-header">
                  <span>
                    <Terminal size={14} /> Python sandbox
                  </span>
                  <button
                    className="icon-button compact"
                    disabled={consoleCode.trim().length === 0 || isCodePending}
                    onClick={runConsoleCode}
                    type="button"
                  >
                    {isCodePending ? <Loader2 size={14} /> : <Send size={14} />}
                  </button>
                </div>
                <textarea
                  aria-label="Python code"
                  onChange={(event) => setConsoleCode(event.target.value)}
                  spellCheck={false}
                  value={consoleCode}
                />
                {consoleError ? <pre className="console-output error">{consoleError}</pre> : null}
                {consoleResult ? (
                  <div className="console-result">
                    <div className="console-meta">
                      exit {consoleResult.exit_code ?? "timeout"} · {consoleResult.duration_ms}ms · network{" "}
                      {consoleResult.network_enabled ? "on" : "off"}
                    </div>
                    {consoleResult.stdout ? (
                      <pre className="console-output">{consoleResult.stdout}</pre>
                    ) : null}
                    {consoleResult.stderr ? (
                      <pre className="console-output error">{consoleResult.stderr}</pre>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}
          <section>
            <h2>Sources</h2>
            {visibleSources.length === 0 ? (
              <p className="muted">Retrieved files appear after a repo-aware answer.</p>
            ) : (
              <div className="source-list">
                {visibleSources.map((context) => (
                  <div className="source-card" key={`${context.path}-${context.start_line}`}>
                    <div className="mono">
                      {context.path}:{context.start_line}-{context.end_line}
                    </div>
                    <div className="muted">score {context.score.toFixed(2)}</div>
                    <ul>
                      {context.reasons.slice(0, 3).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </section>
          {isHostSurface ? (
            <>
              <section>
                <h2>Approvals</h2>
                {approvals.length === 0 ? (
                  <p className="muted">No pending approvals.</p>
                ) : (
                  <div className="source-list">
                    {approvals.slice(0, 5).map((approval) => (
                      <div className="source-card" key={approval.id}>
                        <div>
                          <ShieldAlert size={14} /> {approval.requested_action}
                        </div>
                        <span className="badge warning">{approval.risk_level}</span>
                        <p>{approval.reason}</p>
                      </div>
                    ))}
                  </div>
                )}
              </section>
              <section>
                <h2>Recent Tasks</h2>
                <div className="source-list">
                  {tasks.slice(0, 5).map((task) => (
                    <div className="source-card" key={task.id}>
                      <div>{task.title}</div>
                      <span className="badge">{task.status}</span>
                    </div>
                  ))}
                </div>
              </section>
            </>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}

function RichText({ content }: { content: string }) {
  const parts = parseMarkdownLite(content);
  return (
    <div className="rich-text">
      {parts.map((part, index) => {
        if (part.kind === "code") {
          return (
            <pre key={index}>
              <code>{part.value}</code>
            </pre>
          );
        }
        return part.value.split("\n").map((line, lineIndex) => {
          if (line.trim().startsWith("- ")) {
            return <li key={`${index}-${lineIndex}`}>{line.trim().slice(2)}</li>;
          }
          if (line.trim().length === 0) {
            return <br key={`${index}-${lineIndex}`} />;
          }
          return <p key={`${index}-${lineIndex}`}>{line}</p>;
        });
      })}
    </div>
  );
}

function PendingActivity({
  activity,
  now,
}: {
  activity: ChatPendingActivity | undefined;
  now: number;
}) {
  if (!activity) {
    return (
      <div className="typing">
        <Loader2 size={16} />
        Working locally
      </div>
    );
  }
  const elapsedSeconds = Math.max(
    0,
    Math.floor((now - new Date(activity.startedAt).getTime()) / 1000),
  );
  const steps = pendingSteps(activity, elapsedSeconds);
  return (
    <div className="thinking-panel">
      <div className="thinking-header">
        <span>
          <Loader2 size={16} />
          Working locally
        </span>
        <span>{elapsedSeconds}s</span>
      </div>
      <div className="thinking-meta">
        <span>{activity.repositoryName ?? "No repo selected"}</span>
        <span>{activity.provider}</span>
        <span>{activity.model ?? activity.modelRole}</span>
      </div>
      <ol className="thinking-steps">
        {steps.map((step) => (
          <li className={step.status} key={step.label}>
            <span className="step-dot" />
            <span>{step.label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function pendingSteps(
  activity: ChatPendingActivity,
  elapsedSeconds: number,
): Array<{ label: string; status: "done" | "active" | "waiting" }> {
  const hasRepo = activity.repositoryName !== null && activity.maxBundles > 0;
  const labels = [
    "Checking local policy and request settings",
    hasRepo
      ? `Reading repository context, up to ${activity.maxBundles} files`
      : "Skipping repo retrieval because no repository context is selected",
    hasRepo ? "Ranking exact, symbol, semantic, and path matches" : "Preparing general chat prompt",
    `Calling ${activity.provider} with ${activity.model ?? activity.modelRole}`,
    "Preparing answer and citations",
  ];
  const activeIndex = Math.min(labels.length - 1, Math.floor(elapsedSeconds / 4));
  return labels.map((label, index) => ({
    label,
    status: index < activeIndex ? "done" : index === activeIndex ? "active" : "waiting",
  }));
}

function parseMarkdownLite(content: string): Array<{ kind: "text" | "code"; value: string }> {
  const parts: Array<{ kind: "text" | "code"; value: string }> = [];
  const segments = content.split("```");
  segments.forEach((segment, index) => {
    parts.push({ kind: index % 2 === 0 ? "text" : "code", value: segment });
  });
  return parts;
}

function createThread(repositoryId: string | null): Thread {
  return {
    id: safeRandomUUID(),
    title: "New chat",
    repositoryId,
    messages: [],
    updatedAt: new Date().toISOString(),
  };
}

function loadThreads(): Thread[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as Thread[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function latestSources(messages: ThreadMessage[]): AskContext[] {
  for (const message of [...messages].reverse()) {
    if (message.contexts && message.contexts.length > 0) {
      return message.contexts;
    }
  }
  return [];
}
