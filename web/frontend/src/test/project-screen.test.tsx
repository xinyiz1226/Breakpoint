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
      video_asset_status: "source_expired",
    });
    const getAnalysis = vi.spyOn(api, "getAnalysis");

    render(
      <I18nProvider>
        <ProjectScreen projectId="project-1" />
      </I18nProvider>,
    );

    expect(
      await screen.findByRole("heading", {
        name: "The source video is no longer available.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload & analyze" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a new match" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(getAnalysis).not.toHaveBeenCalled();
  });
});
