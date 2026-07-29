"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "./api";
import type { User } from "./types";

interface AuthValue {
  ready: boolean;
  authenticated: boolean;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    let active = true;
    api.refresh().then((ok) => {
      if (!active) return;
      setAuthenticated(ok);
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const nextUser = await api.login(email, password);
    setUser(nextUser);
    setAuthenticated(true);
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
    () => ({ ready, authenticated, user, login, logout }),
    [authenticated, login, logout, ready, user],
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

  useEffect(() => {
    if (auth.ready && !auth.authenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [auth.authenticated, auth.ready, pathname, router]);

  if (!auth.ready || !auth.authenticated) {
    return <div className="page-status"><span className="spinner" />Checking session…</div>;
  }
  return children;
}
