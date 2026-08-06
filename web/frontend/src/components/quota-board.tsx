"use client";

import { useI18n } from "@/lib/i18n";
import type { Quota } from "@/lib/types";

function ratio(used: number, limit: number) {
  return Math.min(100, limit > 0 ? (used / limit) * 100 : 0);
}

function hours(seconds: number) {
  return `${(seconds / 3600).toFixed(1)}h`;
}

function gigabytes(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function QuotaBoard({ quota }: { quota: Quota }) {
  const { t } = useI18n();
  const rows = [
    {
      label: t("analysis"),
      value: `${hours(quota.monthly_analysis_seconds_used)} / ${hours(quota.monthly_analysis_seconds_limit)}`,
      ratio: ratio(
        quota.monthly_analysis_seconds_used,
        quota.monthly_analysis_seconds_limit,
      ),
    },
    {
      label: t("storage"),
      value: `${gigabytes(quota.storage_bytes_used)} / ${gigabytes(quota.storage_bytes_limit)}`,
      ratio: ratio(quota.storage_bytes_used, quota.storage_bytes_limit),
    },
    {
      label: t("activeJobs"),
      value: `${quota.active_analysis_job_count} / ${quota.max_active_analysis_jobs}`,
      ratio: ratio(quota.active_analysis_job_count, quota.max_active_analysis_jobs),
    },
  ];
  return (
    <aside className="quota-board">
      <p className="set-label">LIVE ALLOCATION</p>
      <h2>{t("quota")}</h2>
      {rows.map((row) => (
        <div className="quota-row" key={row.label}>
          <div><span>{row.label}</span><strong>{row.value}</strong></div>
          <div className="meter"><i style={{ width: `${row.ratio}%` }} /></div>
        </div>
      ))}
    </aside>
  );
}
