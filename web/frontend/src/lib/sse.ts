import type { JobEvent } from "./types";

export interface ParsedEvent {
  id: string | null;
  event: string | null;
  data: string;
}

export function parseSseFrames(buffer: string): {
  events: ParsedEvent[];
  remainder: string;
} {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const remainder = blocks.pop() ?? "";
  const events = blocks.flatMap((block) => {
    let id: string | null = null;
    let event: string | null = null;
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("id:")) id = line.slice(3).trim();
      else if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    return data.length ? [{ id, event, data: data.join("\n") }] : [];
  });
  return { events, remainder };
}

interface StreamOptions {
  url: string;
  getToken: () => string | null;
  refresh: () => Promise<boolean>;
  signal: AbortSignal;
  onEvent: (event: JobEvent, id: string) => void;
  onConnection?: (connected: boolean) => void;
  reconnectDelayMs?: number;
}

class FatalStreamError extends Error {}

export async function streamJobEvents(options: StreamOptions): Promise<void> {
  let lastEventId: string | null = null;
  let delay = options.reconnectDelayMs ?? 500;
  let terminal = false;
  while (!options.signal.aborted) {
    try {
      const token = options.getToken();
      if (!token && !(await options.refresh())) throw new FatalStreamError("Session expired");
      const headers = new Headers({ Accept: "text/event-stream" });
      const currentToken = options.getToken();
      if (currentToken) headers.set("Authorization", `Bearer ${currentToken}`);
      if (lastEventId) headers.set("Last-Event-ID", lastEventId);
      const response = await fetch(options.url, {
        headers,
        credentials: "include",
        signal: options.signal,
      });
      if (response.status === 401 && (await options.refresh())) continue;
      if (!response.ok || !response.body) {
        const message = `Progress stream failed with ${response.status}`;
        if (response.status >= 400 && response.status < 500) {
          throw new FatalStreamError(message);
        }
        throw new Error(message);
      }
      options.onConnection?.(true);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!options.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSseFrames(buffer);
          buffer = parsed.remainder;
          for (const frame of parsed.events) {
            if (!frame.id) continue;
            lastEventId = frame.id;
            let event: JobEvent;
            try {
              event = JSON.parse(frame.data) as JobEvent;
            } catch {
              throw new FatalStreamError("Progress stream returned invalid JSON");
            }
            terminal = ["succeeded", "failed", "cancelled"].includes(event.status);
            options.onEvent(event, frame.id);
          }
        }
      } finally {
        reader.releaseLock();
        options.onConnection?.(false);
      }
    } catch (error) {
      options.onConnection?.(false);
      if (options.signal.aborted) return;
      if (error instanceof FatalStreamError) throw error;
    }
    if (options.signal.aborted || terminal) return;
    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(Math.max(delay * 2, 1), 5000);
  }
}
