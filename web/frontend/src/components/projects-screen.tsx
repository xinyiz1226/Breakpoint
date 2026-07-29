"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Project, Quota } from "@/lib/types";
import { QuotaBoard } from "./quota-board";

export function ProjectsScreen() {
  const { language, t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProjects, nextQuota] = await Promise.all([
        api.listProjects(),
        api.getQuota(),
      ]);
      setProjects(nextProjects);
      setQuota(nextQuota);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name.trim());
      setProjects((current) => [project, ...current]);
      setName("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      setBusy(false);
    }
  }

  async function remove(project: Project) {
    const prompt =
      language === "zh"
        ? `删除“${project.name}”？视频和进行中的任务也会被清理。`
        : `Delete “${project.name}”? Its video and active jobs will be cleaned up.`;
    if (!window.confirm(prompt)) return;
    try {
      await api.deleteProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setQuota(await api.getQuota());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    }
  }

  return (
    <main className="projects-layout">
      <section className="projects-main">
        <div className="page-heading">
          <div>
            <p className="eyebrow">PROJECT HISTORY / SCOREBOARD</p>
            <h1>{t("projects")}</h1>
            <p>{t("projectsIntro")}</p>
          </div>
          <span className="heading-number">{String(projects.length).padStart(2, "0")}</span>
        </div>
        <form className="new-project" onSubmit={create}>
          <label htmlFor="project-name">{t("newProject")}</label>
          <input
            id="project-name"
            placeholder={t("projectName")}
            maxLength={200}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button className="button primary" disabled={busy}>{t("create")}</button>
        </form>
        {error && <div className="inline-error" role="alert">{error}<button onClick={load}>{t("tryAgain")}</button></div>}
        {loading ? (
          <div className="content-status"><span className="spinner" />{t("loading")}</div>
        ) : projects.length === 0 ? (
          <div className="empty-court">
            <div className="mini-court" aria-hidden="true" />
            <h2>{t("noProjects")}</h2>
            <p>{t("noProjectsHint")}</p>
          </div>
        ) : (
          <div className="project-list">
            {projects.map((project, index) => (
              <article className="project-row" key={project.id}>
                <div className="project-index">{String(index + 1).padStart(2, "0")}</div>
                <div className="project-info">
                  <span className={`status-dot ${project.has_video ? "live" : ""}`} />
                  <div>
                    <h2>{project.name}</h2>
                    <p>
                      {new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en", {
                        dateStyle: "medium",
                      }).format(new Date(project.created_at))}
                      {" · "}
                      {project.has_video ? "VIDEO ON COURT" : "AWAITING VIDEO"}
                    </p>
                  </div>
                </div>
                <div className="project-actions">
                  <Link className="button ghost" href={`/projects/${project.id}`}>{t("open")}</Link>
                  <button className="icon-button" onClick={() => remove(project)} aria-label={`${t("delete")} ${project.name}`}>×</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      {quota && <QuotaBoard quota={quota} />}
    </main>
  );
}
