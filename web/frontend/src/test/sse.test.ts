import { describe, expect, it, vi } from "vitest";
import { parseSseFrames, streamJobEvents } from "@/lib/sse";
import type { JobEvent } from "@/lib/types";

function stream(body: string) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
}

describe("authenticated SSE", () => {
  it("keeps partial frames for the next network chunk", () => {
    const parsed = parseSseFrames(
      'id: 4\nevent: progress\ndata: {"status":"running"}\n\nid: 5\ndata: {"sta',
    );
    expect(parsed.events).toEqual([
      { id: "4", event: "progress", data: '{"status":"running"}' },
    ]);
    expect(parsed.remainder).toBe('id: 5\ndata: {"sta');
  });

  it("reconnects with Last-Event-ID and stops on a terminal snapshot", async () => {
    const first =
      'id: 7\nevent: progress\ndata: {"id":"a","status":"running","progress":0.4,"current_step":"vision","failure_summary":null,"finished_at":null}\n\n';
    const second =
      'id: 8\nevent: progress\ndata: {"id":"a","status":"succeeded","progress":1,"current_step":"done","failure_summary":null,"finished_at":"now"}\n\n';
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(stream(first), { status: 200 }))
      .mockResolvedValueOnce(new Response(stream(second), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const events: JobEvent[] = [];

    await streamJobEvents({
      url: "https://api/events",
      getToken: () => "access",
      refresh: async () => true,
      signal: new AbortController().signal,
      onEvent: (event) => events.push(event),
      reconnectDelayMs: 0,
    });

    expect(events.map((event) => event.status)).toEqual(["running", "succeeded"]);
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Last-Event-ID")).toBe("7");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reconnects after a transient network failure", async () => {
    const finished =
      'id: 1\nevent: progress\ndata: {"id":"a","status":"succeeded","progress":1,"current_step":"done","failure_summary":null,"finished_at":"now"}\n\n';
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("network disconnected"))
      .mockResolvedValueOnce(new Response(stream(finished), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const statuses: string[] = [];

    await streamJobEvents({
      url: "https://api/events",
      getToken: () => "access",
      refresh: async () => true,
      signal: new AbortController().signal,
      onEvent: (event) => statuses.push(event.status),
      reconnectDelayMs: 0,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(statuses).toEqual(["succeeded"]);
  });
});
