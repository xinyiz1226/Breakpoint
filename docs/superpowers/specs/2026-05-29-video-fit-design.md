# Video Fit Design

## Goal

Ensure the desktop app review video displays the full frame without cropping the bottom of the video, while keeping playback controls visible and preserving the current review layout.

## Scope

This fix is limited to the renderer video player layout. It does not change analysis logic, clip timing, export logic, the match map, or rally queue behavior.

## Design

The video element should continue using `object-fit: contain` so the entire source frame remains visible. The likely failure is the flex layout around the video and control bar: the video area can be squeezed or clipped by parent overflow, making the bottom of the frame appear cut off.

Update `VideoPlayer` so its root fills the section height, clips only its own rounded container boundary, and splits space explicitly between the flexible video viewport and the fixed-height control bar. The video viewport should be a flex-centered area with `minHeight: 0`, and the video element should use `display: block`, `maxWidth: 100%`, `maxHeight: 100%`, and `objectFit: contain`.

## Error handling

No new runtime errors are introduced. Existing media load and playback behavior remains unchanged.

## Testing

Add or update renderer-flow source checks to guard against regressions in `VideoPlayer` fit behavior. Run the renderer flow test and desktop production build after the change.

## Completion criteria

- Review video frames render fully within the available player area.
- Playback controls remain visible below the video and do not overlay or crop the frame.
- Renderer-flow tests pass.
- Desktop build succeeds.
