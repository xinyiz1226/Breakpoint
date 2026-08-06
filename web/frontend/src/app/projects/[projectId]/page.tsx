import { AppShell } from "@/components/app-shell";
import { ProjectScreen } from "@/components/project-screen";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <AppShell><ProjectScreen projectId={projectId} /></AppShell>;
}
