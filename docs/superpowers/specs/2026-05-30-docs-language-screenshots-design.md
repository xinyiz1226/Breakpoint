# Docs Language Screenshots Design

## Goal

Update the website preview screenshots in `docs/index.html` so English pages use English screenshots and Chinese pages use Chinese screenshots.

## Scope

This change is limited to screenshot image mapping in `docs/index.html`. It does not change screenshot tab behavior, website copy, layout, or image assets.

## Design

Use the existing CSS class model. The default stylesheet represents English, and `body.zh` overrides represent Chinese.

Mappings:

- Default welcome: `Images/Welcome_English.jpg`
- Default analysis: `Images/VideoAnalysis_English.jpg`
- Default editor: `Images/Edit_English.jpg`
- Chinese welcome: `Images/Welcome_Chinese.jpg`
- Chinese analysis: `Images/VideoAnalysis_Chinese.jpg`
- Chinese editor: `Images/Edit_Chinese.jpg`

The existing tab JavaScript should continue to toggle only the tab classes (`analysis-image`, `editor-image`). The language toggle should continue to toggle `body.zh`; CSS will select the correct language-specific background image.

## Testing

Verify that `docs/index.html` references all six expected image files and no longer uses Chinese screenshots as the default English images. Verify that all referenced files exist in `docs/Images`.
