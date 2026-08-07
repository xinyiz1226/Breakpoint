# Progress Score Layout Design

## Goal

Make the analysis progress score readable by giving adjacent digits enough
space and keeping the percent sign immediately to the upper right of the
number at every responsive breakpoint.

## Design

Keep the existing progress value, leading-zero formatting, and component
markup. Treat the number and percent sign as one centered visual group within
`.progress-score`.

- Reduce the number's overly tight negative letter spacing.
- Position the percent sign relative to the score group at its upper-right
  edge instead of aligning it against the full progress panel.
- Preserve the current display typeface, colors, and responsive font sizing.
- Keep the group centered for two-digit values and allow it to expand for
  `100` without overlap.

## Scope

Only the progress score styles in `web/frontend/src/app/globals.css` change.
Progress calculation, polling, localization, and other project screens remain
unchanged.

## Verification

Check that representative values `00`, `25`, `99`, and `100` have distinct
digits, that `%` remains at the number's upper right, and that the group stays
centered without clipping at desktop, tablet, and mobile widths.
