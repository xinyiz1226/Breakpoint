"use client";

import { useState, type ChangeEvent } from "react";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  partCountFor,
  readVideoDuration,
  uploadMultipart,
  validateVideo,
  videoContentType,
  type UploadProgress,
} from "@/lib/upload";
import type { AnalysisJob } from "@/lib/types";
import { formatTime } from "@/lib/rallies";

function bytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

interface Selection {
  file: File;
  duration: number;
}

export function UploadPanel({
  projectId,
  onComplete,
}: {
  projectId: string;
  onComplete: (job: AnalysisJob) => void;
}) {
  const { t } = useI18n();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [reading, setReading] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [finalize, setFinalize] = useState<{
    assetId: string;
    idempotencyKey: string;
    parts: { part_number: number; etag: string }[];
  } | null>(null);

  async function select(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setReading(true);
    setError(null);
    try {
      const duration = await readVideoDuration(file);
      const problem = validateVideo(file, duration);
      if (problem) throw new Error(problem);
      setSelection({ file, duration });
      setFinalize(null);
      setProgress(null);
    } catch (caught) {
      setSelection(null);
      setError(caught instanceof Error ? caught.message : t("unexpected"));
    } finally {
      setReading(false);
      event.target.value = "";
    }
  }

  async function finalizeUpload(request: NonNullable<typeof finalize>) {
    const result = await api.finalizeUpload(projectId, request.assetId, {
      idempotency_key: request.idempotencyKey,
      parts: request.parts,
    });
    onComplete(result.analysis_job);
  }

  async function start() {
    if (!selection) return;
    setBusy(true);
    setError(null);
    try {
      const initiated = await api.initiateUpload(projectId, {
        filename: selection.file.name,
        content_type: videoContentType(selection.file),
        size_bytes: selection.file.size,
        duration_seconds: selection.duration,
        part_count: partCountFor(selection.file.size),
      });
      const completedParts = await uploadMultipart(
        selection.file,
        initiated.part_urls,
        setProgress,
      );
      const request = {
        assetId: initiated.video_asset_id,
        idempotencyKey: crypto.randomUUID(),
        parts: completedParts,
      };
      setFinalize(request);
      await finalizeUpload(request);
    } catch (caught) {
      setError(caught instanceof ApiError || caught instanceof Error ? caught.message : t("unexpected"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="upload-stage">
      <div className="upload-copy">
        <p className="eyebrow">SOURCE VIDEO / ONE MATCH</p>
        <h1>{t("uploadTitle")}</h1>
        <p>{t("uploadIntro")}</p>
      </div>
      <div className={`drop-zone ${selection ? "selected" : ""}`}>
        <input
          id="video-input"
          type="file"
          accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo"
          onChange={select}
          disabled={busy}
        />
        <label htmlFor="video-input">
          <span className="tennis-ball" aria-hidden="true" />
          {reading ? t("preparing") : selection ? t("replaceVideo") : t("chooseVideo")}
        </label>
        {selection && (
          <div className="file-ticket">
            <strong>{selection.file.name}</strong>
            <span>{t("duration")} <b>{formatTime(selection.duration)}</b></span>
            <span>{t("size")} <b>{bytes(selection.file.size)}</b></span>
          </div>
        )}
      </div>
      {progress && (
        <div className="upload-progress">
          <div><span>{t("uploading")}</span><strong>{Math.round(progress.ratio * 100)}%</strong></div>
          <div className="meter"><i style={{ width: `${progress.ratio * 100}%` }} /></div>
          <small>{bytes(progress.uploadedBytes)} / {bytes(progress.totalBytes)}</small>
        </div>
      )}
      {error && (
        <div className="inline-error" role="alert">
          {error}
          {finalize && <button onClick={() => finalizeUpload(finalize)}>{t("retry")}</button>}
        </div>
      )}
      <button className="button primary upload-action" disabled={!selection || busy} onClick={start}>
        {busy ? <><span className="spinner light" />{t("uploading")}</> : t("startUpload")}
      </button>
    </section>
  );
}
