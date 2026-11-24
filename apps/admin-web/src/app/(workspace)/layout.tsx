import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/auth";

/**
 * Full-screen workspaces (live tracking center, cash collection): no sidebar,
 * each page brings its own dark top bar with a way back to the dashboard.
 */
export default async function WorkspaceLayout({ children }: { children: ReactNode }) {
  await getCurrentUser();
  return <div className="flex min-h-screen flex-col bg-background">{children}</div>;
}
