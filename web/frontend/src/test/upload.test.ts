import { describe, expect, it, vi } from "vitest";
import { uploadMultipart, type PartUploader } from "@/lib/upload";

function readBlob(blob: Blob): Promise<number[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve([...new Uint8Array(reader.result as ArrayBuffer)]);
    reader.readAsArrayBuffer(blob);
  });
}

describe("multipart upload", () => {
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
      uploader,
      1,
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
});
