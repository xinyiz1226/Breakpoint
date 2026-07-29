import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, Protected, useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";
import type { User } from "@/lib/types";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/projects",
  useRouter: () => ({ replace }),
}));

const user: User = {
  id: "user-1",
  email: "owner@example.com",
  role: "user",
  is_active: true,
  is_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

function Probe() {
  const auth = useAuth();
  return (
    <>
      <span>{auth.user?.email ?? (auth.authenticated ? "authenticated" : "signed-out")}</span>
      <button onClick={() => void auth.login("owner@example.com", "password")}>login</button>
      <button onClick={() => void api.request("/api/v1/projects").catch(() => undefined)}>
        request
      </button>
    </>
  );
}

describe("AuthProvider recovery", () => {
  afterEach(() => {
    api.setSessionStateHandler(null);
    api.setToken(null);
    replace.mockReset();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("finishes initialization with a recoverable screen after a transient refresh rejection", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));

    render(
      <I18nProvider>
        <AuthProvider>
          <Protected><div>private</div></Protected>
        </AuthProvider>
      </I18nProvider>,
    );

    expect(await screen.findByRole("button", { name: /retry session/i })).toBeInTheDocument();
    expect(screen.queryByText("private")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("clears authenticated user state after a terminal refresh 401", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ access_token: "initial" }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(api, "login").mockResolvedValue(user);

    render(<AuthProvider><Probe /></AuthProvider>);
    await screen.findByText("authenticated");
    fireEvent.click(screen.getByRole("button", { name: "login" }));
    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "request" }));

    await waitFor(() => expect(screen.getByText("signed-out")).toBeInTheDocument());
  });
});
