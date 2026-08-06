import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewStudio } from "@/components/review-studio";
import { api } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";
import type { Rally } from "@/lib/types";

const rally: Rally = {
  id: "rally-1",
  source_index: 0,
  start: 10,
  end: 20,
  score: 2.5,
  features: { hit_count: 8 },
  players: null,
  report_version: "2",
  edit: { included: true, adjusted_start: null, adjusted_end: null },
};

function setup() {
  vi.spyOn(api, "getProject").mockResolvedValue({
    id: "project-1",
    owner_id: "user-1",
    name: "Final",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    has_video: true,
    has_analysis: true,
    video_asset_status: "uploaded",
  });
  vi.spyOn(api, "getRallies").mockResolvedValue([rally]);
  vi.spyOn(api, "sourceUrl").mockResolvedValue({ url: "https://media/source.mp4", expires_in_seconds: 60 });
  vi.spyOn(api, "updateRally").mockImplementation(async (_projectId, _rallyId, edit) => edit);
  return render(<I18nProvider><ReviewStudio projectId="project-1" /></I18nProvider>);
}

describe("rally editing", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });
  it("debounces include edits and surfaces the saved state", async () => {
    setup();
    const checkbox = await screen.findByRole("checkbox");
    vi.useFakeTimers();

    await act(async () => {
      checkbox.click();
      await vi.advanceTimersByTimeAsync(550);
      await Promise.resolve();
    });

    expect(api.updateRally).toHaveBeenCalledWith(
      "project-1",
      "rally-1",
      expect.objectContaining({ included: false }),
    );
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("creates an export snapshot and exposes the signed download", async () => {
    const user = userEvent.setup();
    setup();
    vi.spyOn(api, "createExport").mockResolvedValue({
      id: "export-1",
      project_id: "project-1",
      status: "succeeded",
      progress: 1,
      current_step: "done",
      event_version: 3,
      cancel_requested_at: null,
      selection_snapshot: [{ rally_id: "rally-1", start: 10, end: 20 }],
      output_object_key: "export.mp4",
      output_expires_at: "2026-08-01T00:00:00Z",
      failure_summary: null,
      created_at: "2026-07-29T00:00:00Z",
      started_at: null,
      finished_at: "2026-07-29T00:01:00Z",
    });
    vi.spyOn(api, "exportUrl").mockResolvedValue({
      url: "https://media/export.mp4",
      expires_in_seconds: 60,
    });

    await user.click(await screen.findByRole("button", { name: "Create highlight reel" }));

    const link = await screen.findByRole("link", { name: /Download MP4/ });
    expect(link).toHaveAttribute("href", "https://media/export.mp4");
    expect(window.localStorage.getItem("breakpoint-export:project-1")).toBe("export-1");
  });

  it("flushes pending rally edits before creating an immutable export", async () => {
    const user = userEvent.setup();
    setup();
    const createExport = vi.spyOn(api, "createExport").mockResolvedValue({
      id: "export-2",
      project_id: "project-1",
      status: "queued",
      progress: 0,
      current_step: null,
      event_version: 1,
      cancel_requested_at: null,
      selection_snapshot: [],
      output_object_key: null,
      output_expires_at: null,
      failure_summary: null,
      created_at: "2026-07-29T00:00:00Z",
      started_at: null,
      finished_at: null,
    });
    const startSlider = await screen.findByLabelText(/Start/);
    fireEvent.change(startSlider, { target: { value: "11" } });
    await user.click(screen.getByRole("button", { name: "Create highlight reel" }));

    expect(api.updateRally).toHaveBeenCalledWith(
      "project-1",
      "rally-1",
      expect.objectContaining({ adjusted_start: 11 }),
    );
    expect(vi.mocked(api.updateRally).mock.invocationCallOrder[0]).toBeLessThan(
      createExport.mock.invocationCallOrder[0] ?? Infinity,
    );
  });

  it("freezes every rally edit until delayed export creation returns", async () => {
    const user = userEvent.setup();
    setup();
    let resolveExport: ((job: Awaited<ReturnType<typeof api.createExport>>) => void) | undefined;
    vi.spyOn(api, "createExport").mockImplementation(
      () => new Promise((resolve) => {
        resolveExport = resolve;
      }),
    );
    const exportButton = await screen.findByRole("button", { name: "Create highlight reel" });

    await user.click(exportButton);
    expect(api.createExport).toHaveBeenCalled();
    const checkbox = screen.getByRole("checkbox");
    const startSlider = screen.getByLabelText(/Start/);
    const includeAll = screen.getByRole("button", { name: "Include all" });
    expect(checkbox).toBeDisabled();
    expect(startSlider).toBeDisabled();
    expect(includeAll).toBeDisabled();

    fireEvent.click(checkbox);
    fireEvent.change(startSlider, { target: { value: "12" } });
    fireEvent.click(includeAll);
    expect(api.updateRally).not.toHaveBeenCalled();
    expect(checkbox).toBeChecked();

    await act(async () => {
      resolveExport?.({
        id: "export-delayed",
        project_id: "project-1",
        status: "queued",
        progress: 0,
        current_step: null,
        event_version: 1,
        cancel_requested_at: null,
        selection_snapshot: [{ rally_id: "rally-1", start: 10, end: 20 }],
        output_object_key: null,
        output_expires_at: null,
        failure_summary: null,
        created_at: "2026-07-29T00:00:00Z",
        started_at: null,
        finished_at: null,
      });
      await Promise.resolve();
    });
  });

  it("preserves expired reports as read-only review without playback or export", async () => {
    vi.spyOn(api, "getProject").mockResolvedValue({
      id: "project-1",
      owner_id: "user-1",
      name: "Retained report",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-08T00:00:00Z",
      has_video: false,
      has_analysis: true,
      video_asset_status: "source_expired",
    });
    vi.spyOn(api, "getRallies").mockResolvedValue([rally]);
    const sourceUrl = vi.spyOn(api, "sourceUrl");
    const updateRally = vi.spyOn(api, "updateRally");
    const createExport = vi.spyOn(api, "createExport");

    render(<I18nProvider><ReviewStudio projectId="project-1" /></I18nProvider>);

    expect(await screen.findByText("Rally queue")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Create highlight reel" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a new match" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(sourceUrl).not.toHaveBeenCalled();
    expect(updateRally).not.toHaveBeenCalled();
    expect(createExport).not.toHaveBeenCalled();
  });
});
