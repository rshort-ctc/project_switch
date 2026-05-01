import { ChatWorkspace } from "@/components/chat-workspace";
import {
  getApprovals,
  getHealth,
  getModelGatewayHealth,
  getModelCatalog,
  getModelRoles,
  getRepositories,
  getTasks,
} from "@/lib/api";
import { dashboardSurface } from "@/lib/surface";

export default async function ChatPage() {
  const surface = dashboardSurface();

  if (surface === "web") {
    const [repositories, modelRoles, modelCatalog] = await Promise.all([
      getRepositories(),
      getModelRoles(),
      getModelCatalog(),
    ]);

    return (
      <ChatWorkspace
        approvals={[]}
        health={null}
        modelGateway={null}
        modelCatalog={modelCatalog}
        modelRoles={modelRoles}
        repositories={repositories}
        surface={surface}
        tasks={[]}
      />
    );
  }

  const [repositories, tasks, approvals, health, modelRoles, modelGateway, modelCatalog] = await Promise.all([
    getRepositories(),
    getTasks(),
    getApprovals(),
    getHealth(),
    getModelRoles(),
    getModelGatewayHealth(),
    getModelCatalog(),
  ]);

  return (
    <ChatWorkspace
      approvals={approvals}
      health={health}
      modelGateway={modelGateway}
      modelCatalog={modelCatalog}
      modelRoles={modelRoles}
      repositories={repositories}
      surface={surface}
      tasks={tasks}
    />
  );
}
