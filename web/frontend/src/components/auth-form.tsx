"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LanguageSwitch, useI18n } from "@/lib/i18n";
import { Brand } from "./brand";

type Mode = "login" | "register" | "verify" | "forgot" | "reset";

function safeNextPath(value: string | null): string {
  if (!value?.startsWith("/")) return "/projects";
  try {
    const target = new URL(value, window.location.origin);
    if (target.origin !== window.location.origin) return "/projects";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "/projects";
  }
}

export function AuthForm({ mode }: { mode: Mode }) {
  const { t } = useI18n();
  const auth = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const title =
    mode === "login"
      ? t("signIn")
      : mode === "register"
        ? t("createAccount")
        : mode === "verify"
          ? t("verifyTitle")
          : mode === "forgot"
            ? t("forgotTitle")
            : t("resetTitle");
  const intro =
    mode === "register"
      ? t("registerIntro")
      : mode === "verify"
        ? t("verifyIntro")
        : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "login") {
        await auth.login(email, password);
        router.replace(safeNextPath(search.get("next")));
      } else if (mode === "register") {
        await api.register(email);
        setMessage(t("registrationSent"));
      } else if (mode === "verify") {
        await api.verifyEmail(search.get("token") ?? "", password);
        setMessage(t("verified"));
      } else if (mode === "forgot") {
        await api.forgotPassword(email);
        setMessage(t("forgotSent"));
      } else {
        await api.resetPassword(search.get("token") ?? "", password);
        setMessage(t("resetDone"));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      setBusy(false);
    }
  }

  const needsEmail = mode === "login" || mode === "register" || mode === "forgot";
  const needsPassword = mode === "login" || mode === "verify" || mode === "reset";

  return (
    <main className="auth-layout">
      <section className="auth-hero">
        <div className="auth-top"><Brand /><LanguageSwitch /></div>
        <div className="hero-score">
          <span>01</span>
          <i />
          <span>LOVE</span>
        </div>
        <div>
          <p className="eyebrow">TENNIS FILM ROOM · 2026</p>
          <h1>{t("tagline")}</h1>
          <p className="hero-copy">
            AI match analysis, rally-level decisions, precise trims, and a clean
            highlight reel—without moving your footage through an editing timeline.
          </p>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <p className="set-label">SET 01 / ACCOUNT</p>
          <h2>{title}</h2>
          {intro && <p className="muted">{intro}</p>}
          <form onSubmit={submit}>
            {needsEmail && (
              <label>
                <span>{t("email")}</span>
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
            )}
            {needsPassword && (
              <label>
                <span>{mode === "login" ? t("password") : t("newPassword")}</span>
                <input
                  type="password"
                  minLength={8}
                  maxLength={128}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            )}
            {error && <p className="form-message error" role="alert">{error}</p>}
            {message && <p className="form-message success" role="status">{message}</p>}
            <button className="button primary wide" disabled={busy}>
              {busy ? <span className="spinner light" /> : t("submit")}
            </button>
          </form>
          <div className="auth-links">
            {mode === "login" ? (
              <>
                <Link href="/register">{t("createAccount")}</Link>
                <Link href="/forgot-password">{t("forgotPassword")}</Link>
              </>
            ) : (
              <Link href="/login">{t("backToLogin")}</Link>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
