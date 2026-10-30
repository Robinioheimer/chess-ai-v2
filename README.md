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
