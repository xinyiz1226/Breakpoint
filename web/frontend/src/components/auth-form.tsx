"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LanguageSwitch, useI18n } from "@/lib/i18n";
import { Brand } from "./brand";

type Mode = "login" | "register" | "verify" | "forgot" | "reset";
type LoginNotice = "account-verified" | "password-reset";

function parseLoginNotice(value: string | null): LoginNotice | null {
  return value === "account-verified" || value === "password-reset" ? value : null;
}

function safeNextPath(value: string | null): string {
  if (!value?.startsWith("/")) return "/projects";
  try {
    const origin = "https://breakpoint.local";
    const target = new URL(value, origin);
    if (target.origin !== origin) return "/projects";
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
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMismatch, setPasswordMismatch] = useState(false);
  const [loginNotice, setLoginNotice] = useState<LoginNotice | null>(() =>
    mode === "login" ? parseLoginNotice(search.get("notice")) : null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);
  const noticeValue = search.get("notice");
  const searchString = search.toString();

  useEffect(() => {
    if (mode !== "login" || noticeValue === null) return;
    const nextSearch = new URLSearchParams(searchString);
    nextSearch.delete("notice");
    const query = nextSearch.toString();
    router.replace(query ? `/login?${query}` : "/login");
  }, [mode, noticeValue, router, searchString]);

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
    if ((mode === "verify" || mode === "reset") && password !== confirmPassword) {
      setPasswordMismatch(true);
      confirmPasswordRef.current?.focus();
      confirmPasswordRef.current?.select();
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    if (mode === "login") setLoginNotice(null);
    try {
      if (mode === "login") {
        await auth.login(email, password);
        const next = safeNextPath(search.get("next"));
        window.localStorage.removeItem("breakpoint-auth-next");
        router.replace(next);
      } else if (mode === "register") {
        await api.register(email);
        const next = search.get("next");
        if (next) window.localStorage.setItem("breakpoint-auth-next", safeNextPath(next));
        setMessage(t("registrationSent"));
      } else if (mode === "verify") {
        await api.verifyEmail(search.get("token") ?? "", password);
        const next = window.localStorage.getItem("breakpoint-auth-next");
        router.replace(
          `/login?notice=account-verified${next ? `&next=${encodeURIComponent(next)}` : ""}`,
        );
      } else if (mode === "forgot") {
        await api.forgotPassword(email);
        setMessage(t("forgotSent"));
      } else {
        await api.resetPassword(search.get("token") ?? "", password);
        router.replace("/login?notice=password-reset");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("unexpected"));
    } finally {
      setBusy(false);
    }
  }

  const needsEmail = mode === "login" || mode === "register" || mode === "forgot";
  const needsPassword = mode === "login" || mode === "verify" || mode === "reset";
  const needsPasswordConfirmation = mode === "verify" || mode === "reset";
  const nextQuery = search.get("next");
  const preservedNext = nextQuery ? `?next=${encodeURIComponent(safeNextPath(nextQuery))}` : "";
  const loginNoticeMessage =
    loginNotice === "account-verified"
      ? t("accountVerifiedNotice")
      : loginNotice === "password-reset"
        ? t("passwordResetNotice")
        : null;

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
                  disabled={busy}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setPasswordMismatch(false);
                  }}
                />
              </label>
            )}
            {needsPasswordConfirmation && (
              <label>
                <span>{t("confirmNewPassword")}</span>
                <input
                  ref={confirmPasswordRef}
                  type="password"
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                  required
                  disabled={busy}
                  value={confirmPassword}
                  aria-invalid={passwordMismatch}
                  aria-describedby={passwordMismatch ? "confirm-password-error" : undefined}
                  onChange={(event) => {
                    setConfirmPassword(event.target.value);
                    setPasswordMismatch(false);
                  }}
                  onBlur={() => setPasswordMismatch(password !== confirmPassword)}
                />
                {passwordMismatch && (
                  <span id="confirm-password-error" className="field-error" role="alert">
                    {t("passwordMismatch")}
                  </span>
                )}
              </label>
            )}
            {error && <p className="form-message error" role="alert">{error}</p>}
            {message && <p className="form-message success" role="status">{message}</p>}
            {loginNoticeMessage && (
              <p className="form-message success" role="status">{loginNoticeMessage}</p>
            )}
            <button className="button primary wide" disabled={busy}>
              {busy ? <span className="spinner light" /> : t("submit")}
            </button>
          </form>
          <div className="auth-links">
            {mode === "login" ? (
              <>
                <Link href={`/register${preservedNext}`}>{t("createAccount")}</Link>
                <Link href="/forgot-password">{t("forgotPassword")}</Link>
              </>
            ) : (
              <Link href={`/login${preservedNext}`}>{t("backToLogin")}</Link>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
