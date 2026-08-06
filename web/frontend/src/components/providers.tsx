"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <AuthProvider>{children}</AuthProvider>
    </I18nProvider>
  );
}
