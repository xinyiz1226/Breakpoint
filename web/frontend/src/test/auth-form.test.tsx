import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";

const replace = vi.fn();
const login = vi.fn();
let search = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => search,
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ login }),
}));

function renderForm(mode: "login" | "verify" | "reset") {
  return render(
    <I18nProvider>
      <AuthForm mode={mode} />
    </I18nProvider>,
  );
}

describe("AuthForm password confirmation", () => {
  beforeEach(() => {
    replace.mockReset();
    login.mockReset();
    search = new URLSearchParams();
  });

  it.each(["verify", "reset"] as const)(
    "blocks mismatched %s passwords and clears the field error when edited",
    async (mode) => {
      const user = userEvent.setup();
      const request =
        mode === "verify"
          ? vi.spyOn(api, "verifyEmail").mockResolvedValue({ message: "verified" })
          : vi.spyOn(api, "resetPassword").mockResolvedValue({ message: "reset" });
      search = new URLSearchParams("token=mail-token");
      renderForm(mode);

      const password = screen.getByLabelText("New password");
      const confirmation = screen.getByLabelText("Confirm new password");
      await user.type(password, "password123");
      await user.type(confirmation, "different123");
      fireEvent.blur(confirmation);

      expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
      expect(confirmation).toHaveAttribute("aria-invalid", "true");

      await user.click(screen.getByRole("button", { name: "Continue" }));
      expect(request).not.toHaveBeenCalled();
      expect(confirmation).toHaveFocus();

      await user.clear(confirmation);
      expect(screen.queryByText("Passwords do not match.")).not.toBeInTheDocument();
    },
  );

  it.each([
    ["verify", "account-verified", "verifyEmail"],
    ["reset", "password-reset", "resetPassword"],
  ] as const)(
    "redirects successful %s submission to the matching sign-in notice",
    async (mode, notice, method) => {
      const user = userEvent.setup();
      vi.spyOn(api, method).mockResolvedValue({ message: "ok" });
      search = new URLSearchParams("token=mail-token");
      renderForm(mode);

      await user.type(screen.getByLabelText("New password"), "password123");
      await user.type(screen.getByLabelText("Confirm new password"), "password123");
      await user.click(screen.getByRole("button", { name: "Continue" }));

      await waitFor(() =>
        expect(replace).toHaveBeenCalledWith(`/login?notice=${notice}`),
      );
      expect(api[method]).toHaveBeenCalledWith("mail-token", "password123");
    },
  );

  it("renders a localized one-time login notice and clears it from the URL", async () => {
    const user = userEvent.setup();
    search = new URLSearchParams("notice=account-verified");
    renderForm("login");

    expect(
      screen.getByText(
        "Account verified and password set successfully. Sign in to continue.",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));

    await user.click(screen.getByRole("button", { name: "切换到中文" }));
    expect(
      screen.getByText("邮箱验证和密码设置成功，请登录继续。"),
    ).toBeInTheDocument();
  });

  it("clears the success notice when sign-in starts", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue(undefined);
    search = new URLSearchParams("notice=password-reset");
    renderForm("login");

    await user.type(screen.getByLabelText("Email address"), "player@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(login).toHaveBeenCalledWith("player@example.com", "password123");
    expect(
      screen.queryByText(
        "Password reset successfully. Sign in with your new password.",
      ),
    ).not.toBeInTheDocument();
  });

  it("keeps matching passwords in place when verification fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "verifyEmail").mockRejectedValue(new Error("offline"));
    search = new URLSearchParams("token=mail-token");
    renderForm("verify");

    const password = screen.getByLabelText("New password");
    const confirmation = screen.getByLabelText("Confirm new password");
    await user.type(password, "password123");
    await user.type(confirmation, "password123");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Something went off court.")).toBeInTheDocument();
    expect(password).toHaveValue("password123");
    expect(confirmation).toHaveValue("password123");
    expect(replace).not.toHaveBeenCalled();
  });

  it("ignores and clears an unknown login notice", async () => {
    search = new URLSearchParams("notice=untrusted");
    renderForm("login");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
