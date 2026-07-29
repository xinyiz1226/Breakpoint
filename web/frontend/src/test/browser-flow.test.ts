import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api";
import { uploadMultipart, type PartUploader } from "@/lib/upload";

describe("mocked browser product flow", () => {
  it("covers registration through verified login, upload, edit, and export", async () => {
    const routes: string[] = [];
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      routes.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/register")) return Response.json({ message: "sent" }, { status: 201 });
      if (url.endsWith("/verify-email")) return Response.json({ message: "verified" });
      if (url.endsWith("/login")) {
        return Response.json({
          access_token: "access",
          user: { id: "u1", email: "player@example.com", role: "user", is_active: true, is_verified: true, created_at: "now" },
        });
      }
      if (url.endsWith("/projects") && init?.method === "POST") {
        return Response.json({ id: "p1", owner_id: "u1", name: "Final", created_at: "now", updated_at: "now", has_video: false }, { status: 201 });
      }
      if (url.endsWith("/uploads")) {
        return Response.json({
          video_asset_id: "v1",
          object_key: "source",
          upload_id: "up1",
          part_urls: [{ part_number: 1, url: "https://storage/part", content_length_bytes: 4 }],
          expires_in_seconds: 60,
        }, { status: 201 });
      }
      if (url.endsWith("/finalize")) {
        return Response.json({
          video_asset: { id: "v1", status: "uploaded", retention_expires_at: "later" },
          analysis_job: { id: "a1", project_id: "p1", video_asset_id: "v1", status: "succeeded", progress: 1, current_step: "done", report_object_key: "report", failure_summary: null, event_version: 4, cancel_requested_at: null, created_at: "now", started_at: "now", finished_at: "now" },
        });
      }
      if (url.includes("/rallies/")) return Response.json({ included: true, adjusted_start: 1, adjusted_end: 2 });
      if (url.endsWith("/exports")) {
        return Response.json({ id: "e1", project_id: "p1", status: "queued", progress: 0, current_step: null, event_version: 1, cancel_requested_at: null, selection_snapshot: [{ rally_id: "r1", start: 1, end: 2 }], output_object_key: null, output_expires_at: null, failure_summary: null, created_at: "now", started_at: null, finished_at: null }, { status: 201 });
      }
      return Response.json({ detail: "missing mock" }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();

    await client.register("player@example.com");
    await client.verifyEmail("mail-token", "password123");
    await client.login("player@example.com", "password123");
    const project = await client.createProject("Final");
    const initiated = await client.initiateUpload(project.id, {
      filename: "match.mp4",
      content_type: "video/mp4",
      size_bytes: 4,
      duration_seconds: 120,
      part_count: 1,
    });
    const uploader: PartUploader = async (_part, blob, onProgress) => {
      onProgress(blob.size);
      return "etag";
    };
    const parts = await uploadMultipart(new Blob(["game"]), initiated.part_urls, vi.fn(), {
      upload: uploader,
    });
    const finalized = await client.finalizeUpload(project.id, initiated.video_asset_id, {
      idempotency_key: "flow-key",
      parts,
    });
    await client.updateRally(project.id, "r1", { included: true, adjusted_start: 1, adjusted_end: 2 });
    const exported = await client.createExport(project.id);

    expect(finalized.analysis_job.status).toBe("succeeded");
    expect(exported.selection_snapshot).toHaveLength(1);
    expect(routes).toEqual(expect.arrayContaining([
      expect.stringContaining("/register"),
      expect.stringContaining("/verify-email"),
      expect.stringContaining("/login"),
      expect.stringContaining("/finalize"),
      expect.stringContaining("/rallies/r1"),
      expect.stringContaining("/exports"),
    ]));
  });
});
