import { afterEach, describe, expect, it, vi } from "vitest";
import {
  uploadMultipart,
  uploadPartWithXhr,
  type PartUploader,
} from "@/lib/upload";

function readBlob(blob: Blob): Promise<number[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve([...new Uint8Array(reader.result as ArrayBuffer)]);
    reader.readAsArrayBuffer(blob);
  });
}

describe("multipart upload", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  it("slices by exact server lengths, retries, and reports aggregate progress", async () => {
    vi.useFakeTimers();
    const source = new Blob([new Uint8Array([0, 1, 2, 3, 4, 5, 6, 7])]);
    const attempts = new Map<number, number>();
    const slices: number[][] = [];
    const uploader: PartUploader = vi.fn(async (part, blob, onProgress) => {
      attempts.set(part.part_number, (attempts.get(part.part_number) ?? 0) + 1);
      if (part.part_number === 1 && attempts.get(1) === 1) throw new Error("transient");
      slices.push(await readBlob(blob));
      onProgress(blob.size);
      return `etag-${part.part_number}`;
    });
    const progress: number[] = [];

    const resultPromise = uploadMultipart(
      source,
      [
        { part_number: 1, url: "https://storage/1", content_length_bytes: 3 },
        { part_number: 2, url: "https://storage/2", content_length_bytes: 5 },
      ],
      (value) => progress.push(value.ratio),
      { upload: uploader, concurrency: 1 },
    );
    await vi.runAllTimersAsync();
    const result = await resultPromise;

    expect(slices).toEqual([
      [0, 1, 2],
      [3, 4, 5, 6, 7],
    ]);
    expect(attempts.get(1)).toBe(2);
    expect(result).toEqual([
      { part_number: 1, etag: "etag-1" },
      { part_number: 2, etag: "etag-2" },
    ]);
    expect(progress.at(-1)).toBe(1);
  });

  it("rejects a server plan that does not cover the exact file", async () => {
    await expect(
      uploadMultipart(
        new Blob(["1234"]),
        [{ part_number: 1, url: "x", content_length_bytes: 3 }],
        vi.fn(),
      ),
    ).rejects.toThrow("does not match");
  });

  it("aborts an active XHR and rejects with AbortError", async () => {
    class FakeRequest {
      static current: FakeRequest;
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
      onerror: (() => void) | null = null;
      onabort: (() => void) | null = null;
      onload: (() => void) | null = null;
      status = 0;
      aborted = false;

      constructor() {
        FakeRequest.current = this;
      }

      open() {}
      setRequestHeader() {}
      getResponseHeader() {
        return null;
      }
      send() {}
      abort() {
        this.aborted = true;
        this.onabort?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeRequest);
    const controller = new AbortController();

    const pending = uploadPartWithXhr(
      { part_number: 1, url: "https://storage/1", content_length_bytes: 4 },
      new Blob(["game"]),
      vi.fn(),
      controller.signal,
    );
    const rejection = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();

    await rejection;
    expect(FakeRequest.current.aborted).toBe(true);
  });

  it("stops retry delays and queued parts when cancelled", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const started: number[] = [];
    const completed = new Map<number, string>();
    const uploader: PartUploader = vi.fn(async (part) => {
      started.push(part.part_number);
      throw new Error("offline");
    });

    const pending = uploadMultipart(
      new Blob(["abcdefgh"]),
      [
        { part_number: 1, url: "1", content_length_bytes: 4 },
        { part_number: 2, url: "2", content_length_bytes: 4 },
      ],
      vi.fn(),
      { upload: uploader, concurrency: 1, signal: controller.signal, completedParts: completed },
    );
    const rejection = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(1);
    controller.abort();
    await vi.runAllTimersAsync();

    await rejection;
    expect(started).toEqual([1]);
    expect(completed.size).toBe(0);
  });

  it("reuses completed ETags when retrying failed parts", async () => {
    const completed = new Map<number, string>([[1, '"etag-1"']]);
    const uploader: PartUploader = vi.fn(async (part, blob, onProgress) => {
      onProgress(blob.size);
      return `"etag-${part.part_number}"`;
    });

    const result = await uploadMultipart(
      new Blob(["abcdefgh"]),
      [
        { part_number: 1, url: "1", content_length_bytes: 4 },
        { part_number: 2, url: "2", content_length_bytes: 4 },
      ],
      vi.fn(),
      { upload: uploader, completedParts: completed },
    );

    expect(uploader).toHaveBeenCalledTimes(1);
    expect(result).toEqual([
      { part_number: 1, etag: '"etag-1"' },
      { part_number: 2, etag: '"etag-2"' },
    ]);
  });
});
