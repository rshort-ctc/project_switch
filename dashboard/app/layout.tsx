import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  Boxes,
  ClipboardCheck,
  GitBranch,
  Home,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";

import { dashboardSurface } from "@/lib/surface";

import "./globals.css";

export const metadata: Metadata = {
  title: "SWITCH Dashboard",
  description: "Local coding agent operations dashboard",
};

const navItems = [
  { href: "/", label: "Home", icon: Home },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/repos", label: "Repos", icon: GitBranch },
  { href: "/tasks", label: "Tasks", icon: Boxes },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/audit", label: "Audit", icon: ClipboardCheck },
];

const webNavItems = navItems.filter((item) => item.href === "/chat" || item.href === "/repos");

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const surface = dashboardSurface();
  const visibleNavItems = surface === "web" ? webNavItems : navItems;

  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-title">SWITCH</div>
              <div className="brand-subtitle">
                {surface === "web" ? "Network repo chat" : "Local agent control plane"}
              </div>
            </div>
            <nav className="nav" aria-label="Dashboard navigation">
              {visibleNavItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link href={item.href} key={item.href}>
                    <Icon aria-hidden="true" size={16} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
            <div className="panel" style={{ marginTop: 18 }}>
              <div className="metric">
                <span className="badge success">
                  <Activity aria-hidden="true" size={12} />
                  LOCAL_ONLY
                </span>
                <span className="muted">Backend API only. No direct policy bypass path.</span>
              </div>
            </div>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
