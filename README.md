# Chess AI V2

Native Windows desktop overlay for local chess analysis and training.

## Features
- Resizable, always-on-top PySide6 window
- Interactive legal chessboard with drag-and-drop
- Stockfish UCI analysis in a background worker
- Best-move arrow and source/destination square highlights
- Opacity slider (0–100%)
- Flip board, undo, reset, engine start/stop

The app is designed for local analysis and training. It does not read or control other applications or transmit moves to online games.

## Requirements
- Windows 10/11
- Python 3.11+
- Stockfish executable (download separately from the official Stockfish site)

## Install
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Run
Set the Stockfish executable path in Settings → Stockfish, or set the `STOCKFISH_PATH` environment variable.

```powershell
chess-ai-v2
```

## Tests
```powershell
pytest
```


## Windows EXE build

The Windows executable is built by GitHub Actions with Nuitka. To create a build:

- Open **Actions → Build Windows EXE → Run workflow** for a test artifact.
- For a versioned release, create and push a tag such as `v0.1.0`. The workflow builds `ChessAIV2.exe` and attaches it to the GitHub Release.

The source project remains the development version. User settings are stored separately through Qt `QSettings`, so replacing the executable does not normally remove them. Stockfish is still selected separately in the app; it is not bundled into the executable.

This is the first packaging step, not yet the in-app updater. The updater will later check GitHub Releases, verify the downloaded installer/executable, close the running app, replace the old build, and restart it. Until then, install a new build manually.
