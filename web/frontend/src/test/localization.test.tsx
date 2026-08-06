import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider, LanguageSwitch, useI18n } from "@/lib/i18n";

function CopyProbe() {
  const { t } = useI18n();
  return <p>{t("projects")}</p>;
}

describe("localization", () => {
  it("switches languages and persists the preference", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LanguageSwitch />
        <CopyProbe />
      </I18nProvider>,
    );

    expect(screen.getByText("Match rooms")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "切换到中文" }));

    expect(screen.getByText("比赛空间")).toBeInTheDocument();
    expect(window.localStorage.getItem("breakpoint-language")).toBe("zh");
    expect(document.documentElement.lang).toBe("zh-CN");
  });
});
