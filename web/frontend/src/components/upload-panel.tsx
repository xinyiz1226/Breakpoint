"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
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
import type { AnalysisJob, UploadInitiate } from "@/lib/types";
import { formatTime } from "@/lib/rallies";

function bytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

interface Selection {
  file: File;
  duration: number;
}

interface ActiveUpload {
  initiated: UploadInitiate;
  completedParts: Map<number, string>;
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
  const [abortPending, setAbortPending] = useState(false);
  const [activeUpload, setActiveUpload] = useState<ActiveUpload | null>(null);
  const activeUploadRef = useRef<ActiveUpload | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const [finalize, setFinalize] = useState<{
    assetId: string;
    idempotencyKey: string;
    parts: { part_number: number; etag: string }[];
  } | null>(null);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
      const active = activeUploadRef.current;
      if (active) {
        void api
          .abortUpload(projectId, active.initiated.video_asset_id)
          .catch(() => undefined);
      }
    };
  }, [projectId]);

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
      activeUploadRef.current = null;
      setActiveUpload(null);
      setAbortPending(false);
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

  async function finalizeUpload(
    request: NonNullable<typeof finalize>,
    signal?: AbortSignal,
  ) {
    const result = await api.finalizeUpload(projectId, request.assetId, {
      idempotency_key: request.idempotencyKey,
      parts: request.parts,
    }, signal);
    signal?.throwIfAborted();
    activeUploadRef.current = null;
    if (mountedRef.current) setActiveUpload(null);
    onComplete(result.analysis_job);
  }

  async function start() {
    if (!selection || abortPending) return;
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      let current = activeUpload;
      if (!current) {
        const initiated = await api.initiateUpload(projectId, {
          filename: selection.file.name,
          content_type: videoContentType(selection.file),
          size_bytes: selection.file.size,
          duration_seconds: selection.duration,
          part_count: partCountFor(selection.file.size),
        });
        current = { initiated, completedParts: new Map() };
        activeUploadRef.current = current;
        if (controller.signal.aborted || !mountedRef.current) {
          await api.abortUpload(projectId, initiated.video_asset_id);
          return;
        }
        setActiveUpload(current);
      }
      const completedParts = await uploadMultipart(
        selection.file,
        current.initiated.part_urls,
        setProgress,
        {
          signal: controller.signal,
          completedParts: current.completedParts,
        },
      );
      controller.signal.throwIfAborted();
      const request = {
        assetId: current.initiated.video_asset_id,
        idempotencyKey: crypto.randomUUID(),
        parts: completedParts,
      };
      setFinalize(request);
      await finalizeUpload(request, controller.signal);
    } catch (caught) {
      if (
        mountedRef.current &&
        !(caught instanceof DOMException && caught.name === "AbortError")
      ) {
        setError(caught instanceof ApiError || caught instanceof Error ? caught.message : t("unexpected"));
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      if (mountedRef.current) setBusy(false);
    }
  }

  async function cancel() {
    controllerRef.current?.abort();
    const current = activeUploadRef.current;
    if (!current) return;
    setAbortPending(true);
    setBusy(true);
    setError(null);
    try {
      const result = await api.abortUpload(projectId, current.initiated.video_asset_id);
      if (result.status === "cleanup_pending") {
        setError(t("cleanupPending"));
        return;
      }
      activeUploadRef.current = null;
      setActiveUpload(null);
      setAbortPending(false);
      setProgress(null);
      setFinalize(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("unexpected"));
    } finally {
      if (mountedRef.current) setBusy(false);
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
          disabled={busy || !!activeUpload}
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
          {finalize && !abortPending && <button onClick={() => finalizeUpload(finalize)}>{t("retry")}</button>}
          {!finalize && activeUpload && !abortPending && <button onClick={start}>{t("retry")}</button>}
          {activeUpload && <button onClick={cancel}>{abortPending ? t("retry") : t("cancel")}</button>}
        </div>
      )}
      <div className="upload-actions">
        <button className="button primary upload-action" disabled={!selection || busy || abortPending} onClick={start}>
          {busy ? <><span className="spinner light" />{t("uploading")}</> : t("startUpload")}
        </button>
        {activeUpload && busy && (
          <button className="button ghost" onClick={cancel}>{t("cancel")}</button>
        )}
      </div>
    </section>
  );
}
