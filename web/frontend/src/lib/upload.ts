import type { UploadPartUrl } from "./types";

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024 * 1024;
export const MAX_DURATION_SECONDS = 3 * 60 * 60;
export const TARGET_PART_BYTES = 64 * 1024 * 1024;
const MAX_ATTEMPTS = 3;
const VIDEO_TYPES: Record<string, string> = {
  mp4: "video/mp4",
  mov: "video/quicktime",
  mkv: "video/x-matroska",
  webm: "video/webm",
  avi: "video/x-msvideo",
};

export interface UploadProgress {
  uploadedBytes: number;
  totalBytes: number;
  ratio: number;
}

export function validateVideo(file: File, duration: number): string | null {
  if (!Object.values(VIDEO_TYPES).includes(videoContentType(file))) {
    return "Choose a supported MP4, MOV, MKV, WebM, or AVI video.";
  }
  if (file.size > MAX_UPLOAD_BYTES) return "Video must be 20 GB or smaller.";
  if (!Number.isFinite(duration) || duration <= 0) return "Could not read video duration.";
  if (duration > MAX_DURATION_SECONDS) return "Video must be 3 hours or shorter.";
  return null;
}

export function videoContentType(file: File): string {
  if (Object.values(VIDEO_TYPES).includes(file.type)) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return VIDEO_TYPES[extension] ?? file.type;
}

export function partCountFor(size: number): number {
  return Math.max(1, Math.ceil(size / TARGET_PART_BYTES));
}

export function readVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read video metadata"));
    };
    video.src = url;
  });
}

export type PartUploader = (
  part: UploadPartUrl,
  blob: Blob,
  onProgress: (loaded: number) => void,
) => Promise<string>;

export const uploadPartWithXhr: PartUploader = (part, blob, onProgress) =>
  new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", part.url);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.upload.onprogress = (event) => onProgress(event.loaded);
    request.onerror = () => reject(new Error(`Part ${part.part_number} network error`));
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`Part ${part.part_number} failed with ${request.status}`));
        return;
      }
      const etag = request.getResponseHeader("ETag");
      if (!etag) {
        reject(new Error("Storage did not expose the ETag response header"));
        return;
      }
      onProgress(blob.size);
      resolve(etag);
    };
    request.send(blob);
  });

async function retryPart(
  part: UploadPartUrl,
  blob: Blob,
  upload: PartUploader,
  onProgress: (loaded: number) => void,
): Promise<string> {
  let lastError: Error = new Error("Upload failed");
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      return await upload(part, blob, onProgress);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Upload failed");
      if (attempt < MAX_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, 250 * 2 ** (attempt - 1)));
      }
    }
  }
  throw lastError;
}

export async function uploadMultipart(
  file: Blob,
  parts: UploadPartUrl[],
  onProgress: (progress: UploadProgress) => void,
  upload: PartUploader = uploadPartWithXhr,
  concurrency = 3,
): Promise<{ part_number: number; etag: string }[]> {
  const offsets = new Map<number, number>();
  let offset = 0;
  for (const part of parts) {
    offsets.set(part.part_number, offset);
    offset += part.content_length_bytes;
  }
  if (offset !== file.size) {
    throw new Error("Server part plan does not match the selected file size");
  }

  const loaded = new Map<number, number>();
  const report = () => {
    const uploadedBytes = [...loaded.values()].reduce((sum, value) => sum + value, 0);
    onProgress({ uploadedBytes, totalBytes: file.size, ratio: uploadedBytes / file.size });
  };
  const queue = [...parts];
  const results: { part_number: number; etag: string }[] = [];
  const worker = async () => {
    while (queue.length) {
      const part = queue.shift();
      if (!part) return;
      const start = offsets.get(part.part_number);
      if (start === undefined) throw new Error("Invalid part plan");
      const blob = file.slice(start, start + part.content_length_bytes);
      const etag = await retryPart(part, blob, upload, (bytes) => {
        loaded.set(part.part_number, bytes);
        report();
      });
      results.push({ part_number: part.part_number, etag });
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(concurrency, parts.length) }, () => worker()),
  );
  return results.sort((a, b) => a.part_number - b.part_number);
}
