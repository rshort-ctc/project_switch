export type DashboardSurface = "host" | "web";

export function dashboardSurface(): DashboardSurface {
  return process.env.SWITCH_DASHBOARD_SURFACE === "web" ? "web" : "host";
}

export function isHostSurface(): boolean {
  return dashboardSurface() === "host";
}

export function isWebSurface(): boolean {
  return dashboardSurface() === "web";
}

export function requireHostSurface(action: string): void {
  if (!isHostSurface()) {
    throw new Error(`${action} is only available from the host dashboard.`);
  }
}
