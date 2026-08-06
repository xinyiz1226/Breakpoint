"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { API_URL, ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { streamJobEvents } from "@/lib/sse";
import type { AnalysisJob, JobEvent } from "@/lib/types";

export function JobProgress({
  projectId,
  initial,
}: {
  projectId: string;
  initial: AnalysisJob;
}) {
  const { t } = useI18n();
  const [job, setJob] = useState<AnalysisJob | JobEvent>(initial);
  const [connected, setConnected] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
      return;
    }
    const controller = new AbortController();
    streamJobEvents({
      url: `${API_URL}/api/v1/projects/${projectId}/analysis/events`,
      getToken: () => api.token,
      refresh: () => api.refresh(),
      signal: controller.signal,
      onEvent: setJob,
      onConnection: setConnected,
    }).catch((caught) => {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : t("unexpected"));
      }
    });
    return () => controller.abort();
  }, [job.status, projectId, t]);

  const percent = Math.round(job.progress * 100);
  const statusLabel = t(job.status);

  async function action(kind: "cancel" | "retry") {
    setError(null);
    try {
      setJob(
        kind === "cancel"
          ? await api.cancelAnalysis(projectId)
          : await api.retryAnalysis(projectId),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    }
  }

  return (
    <section className="progress-stage">
      <div className="progress-score">
        <span>{String(percent).padStart(2, "0")}</span><small>%</small>
      </div>
      <div className="progress-content">
        <p className="eyebrow">ANALYSIS / LIVE REPORT</p>
        <h1>{t("progressTitle")}</h1>
        <p className="muted">{t("progressIntro")}</p>
        <div className={`job-status ${job.status}`}>
          <span className="status-dot live" />
          <strong>{statusLabel}</strong>
          <span>{job.current_step ?? "Preparing match"}</span>
        </div>
        <div className="big-meter"><i style={{ width: `${percent}%` }} /></div>
        {!connected && !["succeeded", "failed", "cancelled"].includes(job.status) && (
          <p className="connection-note">{t("reconnecting")}</p>
        )}
        {(job.failure_summary || error) && (
          <div className="inline-error" role="alert">{job.failure_summary ?? error}</div>
        )}
        <div className="progress-actions">
          {(job.status === "queued" || job.status === "running") && (
            <button className="button danger" onClick={() => action("cancel")}>{t("cancel")}</button>
          )}
          {job.status === "failed" && (
            <button className="button primary" onClick={() => action("retry")}>{t("retry")}</button>
          )}
          {job.status === "succeeded" && (
            <Link className="button primary" href={`/projects/${projectId}/review`}>{t("review")} →</Link>
          )}
        </div>
      </div>
    </section>
  );
}
