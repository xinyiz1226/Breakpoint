"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { API_URL, ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  clampTrim,
  effectiveRange,
  formatTime,
  rallyTone,
  recommendedEdit,
} from "@/lib/rallies";
import { streamJobEvents } from "@/lib/sse";
import type { ExportJob, JobEvent, Project, Rally, RallyEdit } from "@/lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";

function hitCount(rally: Rally): string {
  const value = rally.features.hit_count;
  return typeof value === "number" || typeof value === "string" ? String(value) : "—";
}

function updateRally(rallies: Rally[], id: string, edit: RallyEdit): Rally[] {
  return rallies.map((rally) => (rally.id === id ? { ...rally, edit } : rally));
}

function VideoDesk({
  url,
  selected,
  seekRequest,
  onTime,
  onSourceError,
}: {
  url: string;
  selected: Rally | null;
  seekRequest: { time: number; play: boolean; key: number } | null;
  onTime: (value: number) => void;
  onSourceError: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const toggle = useCallback(() => {
    const node = video.current;
    if (!node) return;
    if (node.paused) void node.play();
    else node.pause();
  }, []);

  const skip = useCallback((seconds: number) => {
    const node = video.current;
    if (!node) return;
    node.currentTime = Math.min(node.duration || Infinity, Math.max(0, node.currentTime + seconds));
  }, []);

  useEffect(() => {
    if (!seekRequest || !video.current) return;
    video.current.currentTime = seekRequest.time;
    if (seekRequest.play) void video.current.play();
  }, [seekRequest]);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      if (event.code === "Space") {
        event.preventDefault();
        toggle();
      } else if (event.code === "ArrowLeft") skip(-5);
      else if (event.code === "ArrowRight") skip(5);
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [skip, toggle]);

  const segmentEnd = selected ? effectiveRange(selected).end : null;

  return (
    <section className="video-desk">
      <video
        ref={video}
        src={url}
        playsInline
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onError={onSourceError}
        onTimeUpdate={(event) => {
          const value = event.currentTarget.currentTime;
          setTime(value);
          onTime(value);
          if (segmentEnd !== null && value >= segmentEnd && !event.currentTarget.paused) {
            event.currentTarget.pause();
          }
        }}
      />
      <div className="player-controls">
        <button onClick={() => skip(-10)} aria-label="Back 10 seconds">−10</button>
        <button className="play-button" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "Ⅱ" : "▶"}
        </button>
        <button onClick={() => skip(10)} aria-label="Forward 10 seconds">+10</button>
        <span>{formatTime(time)}</span>
        <input
          aria-label="Video position"
          type="range"
          min={0}
          max={duration || 0}
          step=".1"
          value={Math.min(time, duration || 0)}
          onChange={(event) => {
            if (video.current) video.current.currentTime = Number(event.target.value);
          }}
        />
        <span>{formatTime(duration)}</span>
      </div>
    </section>
  );
}

function MatchMap({
  rallies,
  selectedId,
  onSelect,
}: {
  rallies: Rally[];
  selectedId: string | null;
  onSelect: (rally: Rally) => void;
}) {
  const { t } = useI18n();
  const [suggested, setSuggested] = useState(false);
  const duration = Math.max(...rallies.map((rally) => rally.end), 1);
  const visible = suggested ? rallies.filter((rally) => rallyTone(rally) !== "cut" || rally.edit.included) : rallies;
  return (
    <section className="match-map">
      <div className="section-heading">
        <div><p className="set-label">FULL MATCH / ENERGY</p><h2>{t("matchMap")}</h2></div>
        <div className="tone-legend">
          <span><i className="highlight" />{t("highlight")}</span>
          <span><i className="keep" />{t("keep")}</span>
          <span><i className="cut" />{t("cut")}</span>
        </div>
      </div>
      <div className="map-track">
        {visible.map((rally) => {
          const tone = rallyTone(rally);
          return (
            <button
              key={rally.id}
              className={`${tone} ${selectedId === rally.id ? "selected" : ""}`}
              style={{
                left: `${(rally.start / duration) * 100}%`,
                width: `${Math.max(((rally.end - rally.start) / duration) * 100, .5)}%`,
              }}
              title={`#${rally.source_index + 1} · ${formatTime(rally.start, true)} · ${rally.score.toFixed(2)}`}
              onClick={() => onSelect(rally)}
              aria-label={`Rally ${rally.source_index + 1}`}
            />
          );
        })}
      </div>
      <button className="map-filter" onClick={() => setSuggested((value) => !value)}>
        {suggested ? t("showAll") : t("suggestedOnly")}
      </button>
    </section>
  );
}

function TrimEditor({
  rally,
  saveState,
  disabled,
  onEdit,
  onRetry,
}: {
  rally: Rally;
  saveState: SaveState;
  disabled: boolean;
  onEdit: (edit: RallyEdit) => void;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const range = effectiveRange(rally);
  const change = (edge: "start" | "end") => (event: ChangeEvent<HTMLInputElement>) =>
    onEdit(clampTrim(rally, edge, Number(event.target.value)));
  return (
    <div className="trim-editor">
      <div className="trim-title">
        <strong>{t("trim")}</strong>
        <span className={saveState}>
          {saveState === "saving" ? t("saving") : saveState === "error" ? t("saveFailed") : t("saved")}
        </span>
      </div>
      <label>
        <span>{t("start")} <b>{formatTime(range.start, true)}</b></span>
        <input type="range" min={rally.start} max={rally.end} step=".1" value={range.start} onChange={change("start")} disabled={disabled} />
      </label>
      <label>
        <span>{t("end")} <b>{formatTime(range.end, true)}</b></span>
        <input type="range" min={rally.start} max={rally.end} step=".1" value={range.end} onChange={change("end")} disabled={disabled} />
      </label>
      <div className="trim-actions">
        <button
          disabled={disabled}
          onClick={() => onEdit({ ...rally.edit, adjusted_start: null, adjusted_end: null })}
        >
          {t("reset")}
        </button>
        {saveState === "error" && <button onClick={onRetry} disabled={disabled}>{t("retrySave")}</button>}
      </div>
    </div>
  );
}

function ExportPanel({
  projectId,
  includedCount,
  flushPendingSaves,
  onCreatingChange,
}: {
  projectId: string;
  includedCount: number;
  flushPendingSaves: () => Promise<boolean>;
  onCreatingChange: (locked: boolean) => void;
}) {
  const { t } = useI18n();
  const storageKey = `breakpoint-export:${projectId}`;
  const [job, setJob] = useState<ExportJob | JobEvent | null>(null);
  const [download, setDownload] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const jobId = job?.id;
  const jobStatus = job?.status;

  useEffect(() => {
    const id = window.localStorage.getItem(storageKey);
    if (!id) return;
    api.getExport(projectId, id).then(setJob).catch(() => window.localStorage.removeItem(storageKey));
  }, [projectId, storageKey]);

  useEffect(() => {
    if (!jobId || !jobStatus || !["queued", "running"].includes(jobStatus)) return;
    const controller = new AbortController();
    streamJobEvents({
      url: `${API_URL}/api/v1/projects/${projectId}/exports/${jobId}/events`,
      getToken: () => api.token,
      refresh: () => api.refresh(),
      signal: controller.signal,
      onEvent: setJob,
    }).catch((caught) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : t("unexpected"));
    });
    return () => controller.abort();
  }, [jobId, jobStatus, projectId, t]);

  useEffect(() => {
    if (jobStatus !== "succeeded" || !jobId) return;
    api.exportUrl(projectId, jobId).then((result) => setDownload(result.url)).catch((caught) => {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    });
  }, [jobId, jobStatus, projectId, t]);

  async function create() {
    onCreatingChange(true);
    setBusy(true);
    setError(null);
    try {
      if (!(await flushPendingSaves())) {
        setError(t("saveFailed"));
        return;
      }
      const next = await api.createExport(projectId);
      window.localStorage.setItem(storageKey, next.id);
      setJob(next);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      onCreatingChange(false);
      setBusy(false);
    }
  }

  async function action(kind: "cancel" | "retry") {
    if (!job) return;
    setError(null);
    try {
      setJob(
        kind === "cancel"
          ? await api.cancelExport(projectId, job.id)
          : await api.retryExport(projectId, job.id),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    }
  }

  const active = job && ["queued", "running"].includes(job.status);
  return (
    <div className="export-panel">
      <div>
        <p className="set-label">FINAL SET / EXPORT</p>
        <strong>
          {job?.status === "succeeded"
            ? t("exportReady")
            : active
              ? t("exporting")
              : `${includedCount} ${t("included")}`}
        </strong>
        <small>{t("immutableSnapshot")}</small>
      </div>
      {active && <div className="export-meter"><i style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>}
      {error && <p className="export-error">{error}</p>}
      <div className="export-actions">
        {!job || ["cancelled", "succeeded"].includes(job.status) ? (
          job?.status === "succeeded" && download ? (
            <a className="button primary" href={download} download>{t("download")} ↓</a>
          ) : (
            <button className="button primary" onClick={create} disabled={!includedCount || busy}>
              {t("export")}
            </button>
          )
        ) : active ? (
          <button className="button danger" onClick={() => action("cancel")}>{t("cancel")}</button>
        ) : job.status === "failed" ? (
          <button className="button primary" onClick={() => action("retry")}>{t("retry")}</button>
        ) : null}
      </div>
    </div>
  );
}

export function ReviewStudio({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const tRef = useRef(t);
  tRef.current = t;
  const [project, setProject] = useState<Project | null>(null);
  const [rallies, setRallies] = useState<Rally[]>([]);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourceExpired, setSourceExpired] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [seek, setSeek] = useState<{ time: number; play: boolean; key: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});
  const [exportLocked, setExportLocked] = useState(false);
  const exportLockRef = useRef(false);
  const saveTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const revisions = useRef(new Map<string, number>());
  const savedRevisions = useRef(new Map<string, number>());
  const saveChains = useRef(new Map<string, Promise<void>>());
  const saveRequests = useRef(
    new Map<string, { revision: number; promise: Promise<boolean> }>(),
  );
  const rallyRef = useRef(rallies);
  rallyRef.current = rallies;

  const loadSource = useCallback(async () => {
    try {
      const signed = await api.sourceUrl(projectId);
      setSourceUrl(signed.url);
      setSourceExpired(false);
    } catch (caught) {
      if (caught instanceof ApiError && (caught.status === 404 || caught.status === 409)) {
        setSourceExpired(true);
        return;
      }
      throw caught;
    }
  }, [projectId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProject, nextRallies] = await Promise.all([
        api.getProject(projectId),
        api.getRallies(projectId),
      ]);
      setProject(nextProject);
      setRallies(nextRallies);
      revisions.current = new Map(nextRallies.map((rally) => [rally.id, 0]));
      savedRevisions.current = new Map(nextRallies.map((rally) => [rally.id, 0]));
      setSelectedId(nextRallies[0]?.id ?? null);
      await loadSource();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : tRef.current("unexpected"));
    } finally {
      setLoading(false);
    }
  }, [loadSource, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback((rally: Rally, revision: number): Promise<boolean> => {
    const existing = saveRequests.current.get(rally.id);
    if (existing?.revision === revision) return existing.promise;
    setSaveStates((state) => ({ ...state, [rally.id]: "saving" }));
    const previous = saveChains.current.get(rally.id) ?? Promise.resolve();
    const request = previous.then(async () => {
      try {
        await api.updateRally(projectId, rally.id, rally.edit);
        savedRevisions.current.set(rally.id, revision);
        if (revisions.current.get(rally.id) === revision) {
          setSaveStates((state) => ({ ...state, [rally.id]: "saved" }));
        }
        return true;
      } catch {
        if (revisions.current.get(rally.id) === revision) {
          setSaveStates((state) => ({ ...state, [rally.id]: "error" }));
        }
        return false;
      }
    });
    saveChains.current.set(rally.id, request.then(() => undefined));
    saveRequests.current.set(rally.id, { revision, promise: request });
    void request.then((saved) => {
      const current = saveRequests.current.get(rally.id);
      if (!saved && current?.promise === request) saveRequests.current.delete(rally.id);
    });
    return request;
  }, [projectId]);

  function edit(id: string, nextEdit: RallyEdit) {
    if (exportLockRef.current) return;
    const revision = (revisions.current.get(id) ?? 0) + 1;
    revisions.current.set(id, revision);
    setRallies((current) => updateRally(current, id, nextEdit));
    setSaveStates((state) => ({ ...state, [id]: "saving" }));
    const existing = saveTimers.current.get(id);
    if (existing) clearTimeout(existing);
    saveTimers.current.set(
      id,
      setTimeout(() => {
        const latest = rallyRef.current.find((rally) => rally.id === id);
        if (latest) void save(latest, revision);
      }, 550),
    );
  }

  const flushPendingSaves = useCallback(async () => {
    saveTimers.current.forEach(clearTimeout);
    saveTimers.current.clear();
    const requests = rallyRef.current.flatMap((rally) => {
      const revision = revisions.current.get(rally.id) ?? 0;
      return savedRevisions.current.get(rally.id) === revision
        ? []
        : [save(rally, revision)];
    });
    const results = await Promise.all(requests);
    return results.every(Boolean);
  }, [save]);

  function batch(mode: "all" | "recommended" | "none") {
    if (exportLockRef.current) return;
    for (const rally of rallyRef.current) {
      const next =
        mode === "recommended"
          ? recommendedEdit(rally)
          : { ...rally.edit, included: mode === "all" };
      edit(rally.id, next);
    }
  }

  const selected = rallies.find((rally) => rally.id === selectedId) ?? null;
  const includedCount = rallies.filter((rally) => rally.edit.included).length;
  const setExportLock = (locked: boolean) => {
    exportLockRef.current = locked;
    setExportLocked(locked);
  };
  const select = (rally: Rally, play = true) => {
    setSelectedId(rally.id);
    setSeek({ time: effectiveRange(rally).start, play, key: Date.now() });
  };

  if (loading) return <div className="content-status full"><span className="spinner" />{t("loading")}</div>;
  if (error || !project) return <div className="error-state"><h1>{t("unexpected")}</h1><p>{error}</p><button className="button primary" onClick={load}>{t("tryAgain")}</button></div>;

  return (
    <main className="review-studio">
      <div className="review-titlebar">
        <div><span>REVIEW DESK</span><strong>{project.name}</strong></div>
        <div><b>{includedCount}</b> / {rallies.length} {t("included")}</div>
      </div>
      <div className="review-grid">
        <div className="review-main">
          {sourceUrl ? (
            <VideoDesk
              url={sourceUrl}
              selected={selected}
              seekRequest={seek}
              onTime={setCurrentTime}
              onSourceError={() => {
                setSourceUrl(null);
                void loadSource();
              }}
            />
          ) : (
            <div className="source-expired">
              <span>00:00</span>
              <h1>{t("sourceExpired")}</h1>
              <p>{t("sourceExpiredHint")}</p>
              {!sourceExpired && <button className="button ghost" onClick={loadSource}>{t("tryAgain")}</button>}
            </div>
          )}
          <MatchMap rallies={rallies} selectedId={selectedId} onSelect={select} />
        </div>
        <aside className="rally-panel">
          <div className="rally-panel-head">
            <div><p className="set-label">EDIT DECISIONS</p><h2>{t("rallyQueue")}</h2></div>
            <span>{formatTime(currentTime)}</span>
          </div>
          <div className="batch-actions">
            <button onClick={() => batch("all")} disabled={exportLocked}>{t("includeAll")}</button>
            <button onClick={() => batch("recommended")} disabled={exportLocked}>{t("recommended")}</button>
            <button onClick={() => batch("none")} disabled={exportLocked}>{t("excludeAll")}</button>
          </div>
          <div className="rally-list">
            {rallies.map((rally) => {
              const range = effectiveRange(rally);
              const tone = rallyTone(rally);
              const active = selectedId === rally.id;
              return (
                <article className={`rally-card ${tone} ${active ? "active" : ""} ${rally.edit.included ? "" : "excluded"}`} key={rally.id}>
                  <button className="rally-select" onClick={() => select(rally)}>
                    <span className="rally-number">{String(rally.source_index + 1).padStart(2, "0")}</span>
                    <span>
                      <strong>{t(tone)}</strong>
                      <small>{formatTime(range.start, true)} — {formatTime(range.end, true)} · {hitCount(rally)} HITS</small>
                    </span>
                    <b>{rally.score.toFixed(2)}</b>
                  </button>
                  <label className="include-toggle">
                    <input
                      type="checkbox"
                      checked={rally.edit.included}
                      disabled={exportLocked}
                      onChange={() => edit(rally.id, { ...rally.edit, included: !rally.edit.included })}
                    />
                    <span>{rally.edit.included ? t("keep") : t("cut")}</span>
                  </label>
                  {active && (
                    <TrimEditor
                      rally={rally}
                      saveState={saveStates[rally.id] ?? "saved"}
                      disabled={exportLocked}
                      onEdit={(next) => edit(rally.id, next)}
                      onRetry={() => {
                        if (!exportLockRef.current) {
                          void save(rally, revisions.current.get(rally.id) ?? 0);
                        }
                      }}
                    />
                  )}
                </article>
              );
            })}
          </div>
          <ExportPanel
            projectId={projectId}
            includedCount={includedCount}
            flushPendingSaves={flushPendingSaves}
            onCreatingChange={setExportLock}
          />
        </aside>
      </div>
    </main>
  );
}
