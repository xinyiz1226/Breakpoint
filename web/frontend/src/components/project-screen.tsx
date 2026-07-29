"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AnalysisJob, Project } from "@/lib/types";
import { UploadPanel } from "./upload-panel";
import { JobProgress } from "./job-progress";

export function ProjectScreen({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [project, setProject] = useState<Project | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextProject = await api.getProject(projectId);
      setProject(nextProject);
      if (nextProject.has_analysis) setJob(await api.getAnalysis(projectId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <div className="content-status full"><span className="spinner" />{t("loading")}</div>;
  if (error || !project) {
    return <div className="error-state"><h1>{t("unexpected")}</h1><p>{error}</p><button className="button primary" onClick={load}>{t("tryAgain")}</button></div>;
  }
  const uploadPending = project.video_asset_status
    && ["upload_initiated", "finalizing", "cleanup_pending"].includes(
      project.video_asset_status,
    );
  return (
    <main className="project-workspace">
      <div className="workspace-title"><span>MATCH ROOM</span><strong>{project.name}</strong></div>
      {job ? (
        <JobProgress projectId={projectId} initial={job} />
      ) : project.video_asset_status === "source_expired" ? (
        <section className="error-state">
          <p className="eyebrow">SOURCE RETENTION / 7 DAYS</p>
          <h1>{t("sourceExpired")}</h1>
          <p>{t("sourceExpiredHint")}</p>
          <Link className="button primary" href="/projects">
            {t("createNewMatch")}
          </Link>
        </section>
      ) : uploadPending ? (
        <div className="content-status full">
          <span className="spinner" />
          {t("uploadCancellationPending")}
          <button className="button ghost" onClick={load}>{t("tryAgain")}</button>
        </div>
      ) : (
        <UploadPanel projectId={projectId} onComplete={setJob} />
      )}
    </main>
  );
}
