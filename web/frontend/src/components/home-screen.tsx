"use client";

import Link from "next/link";
import { Brand } from "./brand";
import { useAuth } from "@/lib/auth";
import { LanguageSwitch, useI18n } from "@/lib/i18n";

export function HomeScreen() {
  const auth = useAuth();
  const { t } = useI18n();
  const createPath = "/projects?create=1";
  const createHref = auth.authenticated
    ? createPath
    : `/login?next=${encodeURIComponent(createPath)}`;

  return (
    <main className="landing landing-proof">
      <header>
        <Brand />
        <div className="landing-actions">
          <LanguageSwitch />
          <Link className="button ghost" href={auth.authenticated ? "/projects" : "/login"}>
            {auth.authenticated ? t("projects") : t("signIn")}
          </Link>
        </div>
      </header>

      <div className="landing-proof-grid">
        <section className="landing-proof-copy">
          <p className="eyebrow">{t("homeEyebrow")}</p>
          <h1>
            {t("homeTitleLineOne")}
            <br />
            <em>{t("homeTitleLineTwo")}</em>
          </h1>
          <p className="landing-copy">{t("homeIntro")}</p>
          <div className="landing-cta-row">
            <Link className="button primary" href={createHref}>
              {t("homePrimaryCta")} →
            </Link>
            <span>{t("homeLimitNote")}</span>
          </div>
          <ol className="proof-steps" aria-label={t("homeWorkflow")}>
            {[
              ["01", t("homeStepUpload"), t("homeStepUploadNote")],
              ["02", t("homeStepDetect"), t("homeStepDetectNote")],
              ["03", t("homeStepTrim"), t("homeStepTrimNote")],
              ["04", t("homeStepExport"), t("homeStepExportNote")],
            ].map(([number, title, note]) => (
              <li key={number}>
                <b>{number}</b>
                <strong>{title}</strong>
                <span>{note}</span>
              </li>
            ))}
          </ol>
        </section>

        <aside className="product-proof" aria-label={t("homePreviewLabel")}>
          <div className="proof-caption">
            <span>{t("homePreviewLabel")}</span>
            <span>{t("homePreviewStatus")}</span>
          </div>
          <div className="studio-preview">
            <div className="studio-preview-bar">
              <span>{t("homePreviewPath")}</span>
              <strong>{t("saved")}</strong>
            </div>
            <div className="broadcast-frame">
              <svg viewBox="0 0 1200 650" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
                <rect width="1200" height="650" fill="var(--court-dark)" />
                <path d="M0 0H1200V112C1018 87 820 74 600 74C380 74 182 87 0 112Z" fill="var(--ink)" opacity=".78" />
                <polygon points="274,150 926,150 1110,620 90,620" fill="var(--court)" />
                <g fill="none" stroke="var(--paper-bright)" strokeWidth="5" opacity=".88">
                  <polygon points="274,150 926,150 1110,620 90,620" />
                  <line x1="353" y1="150" x2="229" y2="620" />
                  <line x1="847" y1="150" x2="971" y2="620" />
                  <line x1="300" y1="218" x2="900" y2="218" />
                  <line x1="209" y1="468" x2="991" y2="468" />
                  <line x1="397" y1="306" x2="803" y2="306" />
                  <line x1="600" y1="218" x2="600" y2="468" />
                </g>
                <path d="M173 326H1027" stroke="var(--paper-bright)" strokeWidth="5" />
                <g transform="translate(548 498)">
                  <circle cy="-25" r="12" fill="var(--paper-bright)" />
                  <path d="M-13 -10L12 -12L19 26L-18 26Z" fill="var(--clay)" />
                  <path d="M-12 24L-25 55M14 24L28 55M-10 -5L-35 18M10 -5L43 -31" fill="none" stroke="var(--paper-bright)" strokeWidth="9" strokeLinecap="round" />
                </g>
                <g transform="translate(665 222) scale(.62)">
                  <circle cy="-25" r="12" fill="var(--paper-bright)" />
                  <path d="M-13 -10L12 -12L19 26L-18 26Z" fill="var(--ink)" />
                  <path d="M-12 24L-25 55M14 24L28 55M-10 -5L-35 18M10 -5L36 8" fill="none" stroke="var(--paper-bright)" strokeWidth="9" strokeLinecap="round" />
                </g>
                <circle cx="736" cy="281" r="7" fill="var(--lime)" />
              </svg>
              <span className="preview-play" aria-hidden="true">▶</span>
              <span className="preview-time">00:38:42 / 01:46:18</span>
            </div>
            <div className="preview-map">
              <div><strong>{t("matchMap")}</strong><span>12 / 12</span></div>
              <div className="preview-bars" aria-hidden="true">
                {[34, 19, 27, 39, 34, 27, 19, 34, 27].map((height, index) => (
                  <i key={index} className={index === 3 ? "active" : ""} style={{ height }} />
                ))}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
