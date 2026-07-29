import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api";

describe("ApiClient auth recovery", () => {
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
});
