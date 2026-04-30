import { ChatWorkspace } from "@/components/chat-workspace";
import {
  getApprovals,
  getHealth,
  getModelGatewayHealth,
  getModelRoles,
  getRepositories,
  getTasks,
} from "@/lib/api";

export default async function ChatPage() {
  const [repositories, tasks, approvals, health, modelRoles, modelGateway] = await Promise.all([
    getRepositories(),
    getTasks(),
    getApprovals(),
    getHealth(),
    getModelRoles(),
    getModelGatewayHealth(),
  ]);

  return (
    <ChatWorkspace
      approvals={approvals}
      health={health}
      modelGateway={modelGateway}
      modelRoles={modelRoles}
      repositories={repositories}
      tasks={tasks}
    />
  );
}
