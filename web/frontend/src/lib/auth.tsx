"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "./api";
import { useI18n } from "./i18n";
import type { User } from "./types";

interface AuthValue {
  ready: boolean;
  authenticated: boolean;
  user: User | null;
  recoveryError: string | null;
  retrySession: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const retrySession = useCallback(async () => {
    setReady(false);
    setRecoveryError(null);
    try {
      const ok = await api.refresh();
      if (!mountedRef.current) return;
      setAuthenticated(ok);
      if (!ok) setUser(null);
    } catch {
      if (!mountedRef.current) return;
      setAuthenticated(false);
      setUser(null);
      setRecoveryError("Session recovery is temporarily unavailable.");
    } finally {
      if (mountedRef.current) setReady(true);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    api.setSessionStateHandler((state) => {
      if (!mountedRef.current) return;
      setAuthenticated(false);
      setUser(null);
      setReady(true);
      setRecoveryError(
        state === "unavailable"
          ? "Session recovery is temporarily unavailable."
          : null,
      );
    });
    void retrySession();
    return () => {
      mountedRef.current = false;
      api.setSessionStateHandler(null);
    };
  }, [retrySession]);

  const login = useCallback(async (email: string, password: string) => {
    const nextUser = await api.login(email, password);
    setUser(nextUser);
    setAuthenticated(true);
    setRecoveryError(null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setAuthenticated(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      ready,
      authenticated,
      user,
      recoveryError,
      retrySession,
      login,
      logout,
    }),
    [authenticated, login, logout, ready, recoveryError, retrySession, user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function Protected({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useI18n();

  useEffect(() => {
    if (auth.ready && !auth.authenticated && !auth.recoveryError) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [auth.authenticated, auth.ready, auth.recoveryError, pathname, router]);

  if (!auth.ready) {
    return <div className="page-status"><span className="spinner" />{t("checkingSession")}</div>;
  }
  if (auth.recoveryError) {
    return (
      <div className="error-state">
        <h1>{t("sessionUnavailable")}</h1>
        <button className="button primary" onClick={() => void auth.retrySession()}>
          {t("retrySession")}
        </button>
      </div>
    );
  }
  if (!auth.authenticated) {
    return <div className="page-status"><span className="spinner" />{t("checkingSession")}</div>;
  }
  return children;
}
