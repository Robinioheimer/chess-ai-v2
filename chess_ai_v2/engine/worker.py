from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
import chess
import chess.engine


class EngineWorker(QObject):
    best_move = Signal(str, str, str)  # UCI move, score text, principal variation
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, executable: str, depth: int = 15) -> None:
        super().__init__()
        self.executable = executable
        self.depth = max(1, min(depth, 30))
        self._engine: chess.engine.SimpleEngine | None = None
        self._board = chess.Board()
        self._running = False

    @Slot()
    def start(self) -> None:
        if self._running:
            return
        try:
            path = self.executable or os.environ.get("STOCKFISH_PATH", "")
            if not path or not Path(path).is_file():
                self.status.emit("Stockfish-Pfad fehlt")
                return
            self._engine = chess.engine.SimpleEngine.popen_uci(path)
            self._running = True
            self.status.emit("Stockfish verbunden")
            self.analyze()
        except Exception as exc:
            self.failed.emit(str(exc))
            self.status.emit("Engine-Fehler")

    @Slot(str)
    def set_position(self, fen: str) -> None:
        try:
            self._board = chess.Board(fen)
            if self._running:
                self.analyze()
        except ValueError as exc:
            self.failed.emit(f"Ungültige Stellung: {exc}")

    @Slot()
    def analyze(self) -> None:
        if not self._running or self._engine is None or self._board.is_game_over():
            return
        try:
            info = self._engine.analyse(self._board, chess.engine.Limit(depth=self.depth))
            pv = info.get("pv", [])
            if not pv:
                return
            move = pv[0]
            score = info.get("score")
            score_text = score.pov(self._board.turn).score(mate_score=100000) if score else 0
            pv_text = " ".join(self._board.variation_san(pv[:8]))
            self.best_move.emit(move.uci(), str(score_text), pv_text)
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def stop(self) -> None:
        self._running = False
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                self._engine.close()
            self._engine = None
        self.status.emit("Stockfish gestoppt")
