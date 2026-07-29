import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectScreen } from "@/components/project-screen";
import { api } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";

describe("ProjectScreen upload state", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns an aborted project to upload instead of requesting missing analysis", async () => {
    vi.spyOn(api, "getProject").mockResolvedValue({
      id: "project-1",
      owner_id: "user-1",
      name: "Restartable",
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z",
      has_video: false,
      has_analysis: false,
      video_asset_status: "upload_aborted",
    });
    const getAnalysis = vi.spyOn(api, "getAnalysis");

    render(
      <I18nProvider>
        <ProjectScreen projectId="project-1" />
      </I18nProvider>,
    );

    expect(await screen.findByRole("button", { name: "Upload & analyze" })).toBeInTheDocument();
    expect(getAnalysis).not.toHaveBeenCalled();
  });

  it("routes an expired historical project to new-project creation", async () => {
    vi.spyOn(api, "getProject").mockResolvedValue({
      id: "project-1",
      owner_id: "user-1",
      name: "Historical match",
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-08-05T00:00:00Z",
      has_video: false,
      has_analysis: true,
      video_asset_status: "source_expired",
    });
    const getAnalysis = vi.spyOn(api, "getAnalysis").mockResolvedValue({
      id: "analysis-1",
      project_id: "project-1",
      video_asset_id: "asset-1",
      status: "succeeded",
      progress: 1,
      current_step: "Report ready",
      report_object_key: "projects/project-1/reports/report.json",
      failure_summary: null,
      event_version: 3,
      cancel_requested_at: null,
      created_at: "2026-07-29T00:00:00Z",
      started_at: "2026-07-29T00:01:00Z",
      finished_at: "2026-07-29T00:02:00Z",
    });

    render(
      <I18nProvider>
        <ProjectScreen projectId="project-1" />
      </I18nProvider>,
    );

    expect(await screen.findByRole("link", { name: /review/i })).toHaveAttribute(
      "href",
      "/projects/project-1/review",
    );
    expect(screen.queryByRole("button", { name: "Upload & analyze" })).not.toBeInTheDocument();
    expect(getAnalysis).toHaveBeenCalledWith("project-1");
  });
});
