import type { Rally, RallyEdit } from "./types";

export const INCLUDE_THRESHOLD = 1.7;
export const HIGHLIGHT_THRESHOLD = 2.3;
export const MIN_SEGMENT_DURATION = 0.5;

export type RallyTone = "highlight" | "keep" | "cut";

export function effectiveRange(rally: Rally): { start: number; end: number } {
  return {
    start: rally.edit.adjusted_start ?? rally.start,
    end: rally.edit.adjusted_end ?? rally.end,
  };
}

export function rallyTone(rally: Rally): RallyTone {
  if (rally.score > HIGHLIGHT_THRESHOLD) return "highlight";
  if (rally.score > INCLUDE_THRESHOLD) return "keep";
  return "cut";
}

export function recommendedEdit(rally: Rally): RallyEdit {
  return {
    included: rally.score > INCLUDE_THRESHOLD,
    adjusted_start: null,
    adjusted_end: null,
  };
}

export function clampTrim(
  rally: Rally,
  edge: "start" | "end",
  value: number,
): RallyEdit {
  const current = effectiveRange(rally);
  const start =
    edge === "start"
      ? Math.min(Math.max(value, rally.start), current.end - MIN_SEGMENT_DURATION)
      : current.start;
  const end =
    edge === "end"
      ? Math.max(Math.min(value, rally.end), current.start + MIN_SEGMENT_DURATION)
      : current.end;
  return {
    ...rally.edit,
    adjusted_start: start === rally.start ? null : Number(start.toFixed(2)),
    adjusted_end: end === rally.end ? null : Number(end.toFixed(2)),
  };
}

export function formatTime(seconds: number, precise = false): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder
    .toFixed(precise ? 1 : 0)
    .padStart(precise ? 4 : 2, "0")}`;
}
