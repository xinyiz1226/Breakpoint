# Desktop Analysis Completion Fix

## Goal

Make packaged desktop analysis enter the review screen immediately after the
analysis report is ready, without silently compiling a highlight video first.
Also show the installed application version on the analysis screen instead of
the stale hard-coded version.

## Root Cause

The packaged engine uses `TennisHighlightAnalysis.py`, whose default behavior
compiles all selected segments after `run_analysis()` returns. The Electron
bridge starts that executable without `--no-compile` and waits for the process
to exit. Although the engine has already emitted the final analysis progress,
the UI remains on stage four while FFmpeg performs an unnecessary pre-review
export.

The analysis screen separately renders a hard-coded `v0.1.6`, while the welcome
screen already obtains the package version through the `get-app-version` IPC
handler.

## Design

### Analysis and Export Separation

Add `--no-compile` to the arguments passed by the Electron Python bridge. This
changes only desktop analysis behavior:

- analysis generates `full_report.json`;
- the engine process exits after analysis;
- Electron loads the report and opens the review screen;
- video compilation remains exclusively in the existing user-triggered export
  flow after clip selection and trimming.

The standalone packaged engine keeps its current default compilation behavior
when invoked outside the desktop bridge.

### Version Display

Replace the analysis screen's hard-coded version with the value returned by the
existing `window.api.getAppVersion()` API. Follow the welcome screen's existing
version-loading pattern so both screens use package metadata as the source of
truth.

If version retrieval has not completed, render the existing neutral fallback
`0.0.0`; do not block analysis or introduce a new error state for cosmetic
metadata.

## Error Handling

The existing analysis process and export error paths remain unchanged.
`--no-compile` is already supported by the packaged engine entry point. Export
failures continue to surface only when the user explicitly exports.

## Testing

Add focused regression coverage that verifies:

1. the desktop bridge invokes packaged analysis with `--no-compile`;
2. the analysis screen no longer contains a hard-coded product version and
   uses the application version API;
3. existing renderer flow tests and the desktop TypeScript build continue to
   pass.

No algorithm, ranking, report schema, or export-selection behavior changes.
