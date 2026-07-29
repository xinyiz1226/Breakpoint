import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api";

describe("ApiClient auth recovery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });
  it("rotates the refresh cookie and retries one unauthorized request", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        Response.json({ access_token: "rotated", token_type: "bearer" }),
      )
      .mockResolvedValueOnce(Response.json([{ id: "project-1" }]));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setToken("expired");

    const result = await client.request<{ id: string }[]>("/api/v1/projects");

    expect(result[0]?.id).toBe("project-1");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      credentials: "include",
    });
    const retryHeaders = fetchMock.mock.calls[2]?.[1]?.headers;
    expect(new Headers(retryHeaders).get("Authorization")).toBe("Bearer rotated");
  });

  it("coalesces concurrent refresh attempts", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(pending);
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();

    const first = client.refresh();
    const second = client.refresh();
    resolveResponse?.(Response.json({ access_token: "one" }));

    await expect(Promise.all([first, second])).resolves.toEqual([true, true]);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("invalidates the session when the refresh cookie is expired or revoked", async () => {
    const client = new ApiClient();
    client.setToken("stale");
    const sessionState = vi.fn();
    client.setSessionStateHandler(sessionState);
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(client.refresh()).resolves.toBe(false);

    expect(client.token).toBeNull();
    expect(sessionState).toHaveBeenCalledWith("invalidated");
  });

  it("reports transient refresh failures without treating them as a logged-out session", async () => {
    const client = new ApiClient();
    client.setToken("stale");
    const sessionState = vi.fn();
    client.setSessionStateHandler(sessionState);
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));

    await expect(client.refresh()).rejects.toThrow("offline");

    expect(client.token).toBeNull();
    expect(sessionState).toHaveBeenCalledWith("unavailable");
    expect(sessionState).not.toHaveBeenCalledWith("invalidated");
  });

  it("does not let a delayed account-A refresh replace an account-B login", async () => {
    let resolveRefresh: ((response: Response) => void) | undefined;
    const delayedRefresh = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(delayedRefresh)
      .mockResolvedValueOnce(
        Response.json({
          access_token: "account-b",
          user: {
            id: "user-b",
            email: "b@example.com",
            role: "user",
            is_active: true,
            is_verified: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(Response.json([]));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();

    const staleRefresh = client.refresh();
    expect(client.sessionEpoch).toBe(0);
    await client.login("b@example.com", "password");
    expect(client.sessionEpoch).toBe(1);
    resolveRefresh?.(Response.json({ access_token: "account-a" }));
    await expect(staleRefresh).resolves.toBe(false);
    expect(client.token).toBe("account-b");
    await client.request("/api/v1/projects");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/v1/auth/refresh",
      "http://localhost:8000/api/v1/auth/login",
      "http://localhost:8000/api/v1/projects",
    ]);
    const requestHeaders = fetchMock.mock.calls.at(-1)?.[1]?.headers;
    const authorization = new Headers(requestHeaders).get("Authorization");
    expect(authorization?.split(" ").at(-1)).toBe(client.token);
  });
});
