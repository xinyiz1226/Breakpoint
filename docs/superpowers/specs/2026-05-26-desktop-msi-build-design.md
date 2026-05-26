# Desktop MSI build script design

## Goal

Make the desktop packaging command run once and produce a Windows MSI without the manual fixes needed during the previous build.

The default command remains:

```powershell
python desktop\scripts\package.py
```

## Scope

- Package MSI only by default.
- Keep `build_engine.py` responsible for building the Python engine.
- Make `package.py` responsible for orchestration, dependency checks, Windows-safe command execution, Electron Builder invocation, and artifact verification.
- Preserve existing Electron Builder configuration except for command-line overrides needed by the packaging pipeline.

## Design

`desktop/scripts/package.py` becomes the recommended one-shot packaging entry point. It will:

1. Resolve project paths from the script location so it can run from any working directory.
2. Check for `desktop/node_modules`; if missing, run `npm.cmd ci` on Windows or `npm ci` elsewhere.
3. Build the Python engine with the current interpreter by invoking `desktop/scripts/build_engine.py`.
4. Verify required bundled resources exist, including `dist-engine/TennisHighlightAnalysis/TennisHighlightAnalysis.exe` and `dist-engine/ffmpeg/ffmpeg.exe`.
5. Build the Electron renderer/main/preload assets with `npm.cmd run build` on Windows.
6. Run Electron Builder for the `msi` target only, with `CSC_IDENTITY_AUTO_DISCOVERY=false`.
7. Use a short default output directory on Windows, `C:\bp-msi`, to avoid WiX failures from long generated file paths. Allow overriding this path with a command-line option.
8. Prepare Electron Builder's `winCodeSign` cache when possible so extraction does not fail on Windows accounts without symlink privileges.
9. Verify the produced `.msi` exists and print its full path and size.

## Error handling

The script should fail fast with actionable messages:

- Missing Node.js, npm, Python, PyInstaller, or Electron Builder dependency: print the command that failed.
- Missing engine output or ffmpeg: print the exact expected path.
- Electron Builder file-lock failures: recommend closing running app instances or changing the output directory.
- WiX long-path failures: default output already avoids this; custom output users should be told to use a shorter path.

## Testing

Validate by running:

```powershell
python desktop\scripts\package.py
```

Success means the command exits with code 0 and prints a verified MSI path.
