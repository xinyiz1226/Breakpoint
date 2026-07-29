import { act, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UploadPanel } from "@/components/upload-panel";
import { api } from "@/lib/api";

const uploadMocks = vi.hoisted(() => ({
  readVideoDuration: vi.fn(),
  uploadMultipart: vi.fn(),
}));

vi.mock("@/lib/i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("@/lib/upload", async () => ({
  ...(await vi.importActual<typeof import("@/lib/upload")>("@/lib/upload")),
  readVideoDuration: uploadMocks.readVideoDuration,
  uploadMultipart: uploadMocks.uploadMultipart,
}));

describe("UploadPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("aborts the server upload when navigation unmounts an initiated transfer", async () => {
    uploadMocks.readVideoDuration.mockResolvedValue(120);
    const initiateUpload = vi.spyOn(api, "initiateUpload").mockResolvedValue({
      video_asset_id: "asset-1",
      object_key: "source/video.mp4",
      upload_id: "upload-1",
      part_urls: [{ part_number: 1, url: "https://storage/1", content_length_bytes: 4 }],
      expires_in_seconds: 900,
    });
    vi.spyOn(api, "abortUpload").mockResolvedValue({ status: "aborted" });
    uploadMocks.uploadMultipart.mockImplementationOnce(
      (_file, _parts, _progress, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }),
    );

    const screen = render(<UploadPanel projectId="project-1" onComplete={vi.fn()} />);
    const input = screen.container.querySelector<HTMLInputElement>("#video-input");
    expect(input).not.toBeNull();
    const file = new File(["game"], "match.mp4", { type: "video/mp4" });
    Object.defineProperty(file, "size", { value: 4 });
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file] });
      input?.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      screen.getByRole("button", { name: "startUpload" }).click();
    });
    expect(uploadMocks.uploadMultipart).toHaveBeenCalled();

    screen.unmount();
    await act(async () => {
      await Promise.resolve();
    });

    expect(api.abortUpload).toHaveBeenCalledWith("project-1", "asset-1");

    uploadMocks.uploadMultipart.mockResolvedValueOnce([
      { part_number: 1, etag: '"etag-restarted"' },
    ]);
    vi.spyOn(api, "finalizeUpload").mockResolvedValue({
      video_asset: {
        id: "asset-1",
        status: "uploaded",
        retention_expires_at: "2026-08-05T00:00:00Z",
      },
      analysis_job: {
        id: "job-restarted",
        project_id: "project-1",
        video_asset_id: "asset-1",
        status: "queued",
        progress: 0,
        current_step: null,
        report_object_key: null,
        failure_summary: null,
        event_version: 0,
        cancel_requested_at: null,
        created_at: "2026-07-29T00:00:00Z",
        started_at: null,
        finished_at: null,
      },
    });
    const onComplete = vi.fn();
    const revisit = render(<UploadPanel projectId="project-1" onComplete={onComplete} />);
    const revisitInput = revisit.container.querySelector<HTMLInputElement>("#video-input");
    await act(async () => {
      Object.defineProperty(revisitInput, "files", { value: [file] });
      revisitInput?.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      revisit.getByRole("button", { name: "startUpload" }).click();
      await Promise.resolve();
    });

    expect(initiateUpload).toHaveBeenCalledTimes(2);
    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(
        expect.objectContaining({ id: "job-restarted" }),
      );
    });
    revisit.unmount();
  });

  it("cancels an in-flight finalize without reporting false success", async () => {
    uploadMocks.readVideoDuration.mockResolvedValue(120);
    uploadMocks.uploadMultipart.mockResolvedValue([
      { part_number: 1, etag: '"etag-1"' },
    ]);
    vi.spyOn(api, "initiateUpload").mockResolvedValue({
      video_asset_id: "asset-finalizing",
      object_key: "source/video.mp4",
      upload_id: "upload-finalizing",
      part_urls: [{ part_number: 1, url: "https://storage/1", content_length_bytes: 4 }],
      expires_in_seconds: 900,
    });
    vi.spyOn(api, "abortUpload").mockResolvedValue({ status: "cleanup_pending" });
    let finalizeSignal: AbortSignal | undefined;
    vi.spyOn(api, "finalizeUpload").mockImplementation(
      (_projectId, _assetId, _input, signal) =>
        new Promise((_resolve, reject) => {
          finalizeSignal = signal;
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }),
    );
    const onComplete = vi.fn();
    const view = render(<UploadPanel projectId="project-1" onComplete={onComplete} />);
    const input = view.container.querySelector<HTMLInputElement>("#video-input");
    const file = new File(["game"], "match.mp4", { type: "video/mp4" });
    Object.defineProperty(file, "size", { value: 4 });
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file] });
      input?.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      view.getByRole("button", { name: "startUpload" }).click();
      await Promise.resolve();
    });

    await act(async () => {
      view.getByRole("button", { name: "cancel" }).click();
      await Promise.resolve();
    });

    expect(finalizeSignal?.aborted).toBe(true);
    expect(api.abortUpload).toHaveBeenCalledWith("project-1", "asset-finalizing");
    expect(onComplete).not.toHaveBeenCalled();

    const failedAbort = Promise.reject(new Error("offline"));
    void failedAbort.catch(() => undefined);
    const catchRejection = vi.spyOn(failedAbort, "catch");
    vi.mocked(api.abortUpload).mockReturnValueOnce(failedAbort);
    view.unmount();
    await act(async () => {
      await Promise.resolve();
    });
    expect(catchRejection).toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });
});
