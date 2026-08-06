"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Protected, useAuth } from "@/lib/auth";
import { LanguageSwitch, useI18n } from "@/lib/i18n";
import { Brand } from "./brand";

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const auth = useAuth();
  const router = useRouter();
  return (
    <Protected>
      <div className="app-frame">
        <header className="app-header">
          <Brand compact />
          <nav aria-label="Primary navigation">
            <Link href="/projects">{t("projects")}</Link>
          </nav>
          <div className="header-actions">
            <LanguageSwitch />
            <button
              className="text-button"
              onClick={async () => {
                await auth.logout();
                router.replace("/login");
              }}
            >
              {t("logout")}
            </button>
          </div>
        </header>
        {children}
      </div>
    </Protected>
  );
}
