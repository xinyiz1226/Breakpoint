import { act, render } from "@testing-library/react";
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
    vi.spyOn(api, "initiateUpload").mockResolvedValue({
      video_asset_id: "asset-1",
      object_key: "source/video.mp4",
      upload_id: "upload-1",
      part_urls: [{ part_number: 1, url: "https://storage/1", content_length_bytes: 4 }],
      expires_in_seconds: 900,
    });
    vi.spyOn(api, "abortUpload").mockResolvedValue({ status: "aborted" });
    uploadMocks.uploadMultipart.mockImplementation(
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
  });
});
