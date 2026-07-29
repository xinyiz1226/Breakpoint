import { AppShell } from "@/components/app-shell";
import { ReviewStudio } from "@/components/review-studio";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <AppShell><ReviewStudio projectId={projectId} /></AppShell>;
}
