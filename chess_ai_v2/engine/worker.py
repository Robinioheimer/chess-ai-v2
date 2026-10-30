from __future__ import annotations

import os
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
import chess
import chess.engine


class EngineWorker(QObject):
    best_move = Signal(str, str, str)  # UCI move, score text, principal variation
    candidate_moves = Signal(str)  # JSON list: UCI, exact Stockfish score, PV
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, executable: str, depth: int = 15, multipv: int = 3) -> None:
        super().__init__()
        self.executable = executable
        self.depth = max(1, min(depth, 30))
        self.multipv = max(1, min(int(multipv), 3))
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

    @Slot(int)
    def set_multipv(self, value: int) -> None:
        self.multipv = max(1, min(int(value), 3))
        if self._running:
            self.analyze()

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
            infos = self._engine.analyse(
                self._board,
                chess.engine.Limit(depth=self.depth),
                multipv=self.multipv,
            )
            if isinstance(infos, dict):
                infos = [infos]
            results = []
            for info in infos[:self.multipv]:
                pv = info.get("pv", [])
                if not pv:
                    continue
                score = info.get("score")
                pov_score = score.pov(self._board.turn) if score else chess.engine.Score(0)
                cp = pov_score.score(mate_score=10000)
                # Exakte Stockfish-Bewertung in Centipawns bzw. Mattangabe.
                # Perspektive bleibt die Seite, die in dieser Stellung am Zug ist.
                if pov_score.is_mate():
                    mate = pov_score.mate()
                    score_text = f"#{mate}" if mate is not None and mate > 0 else f"-#{abs(mate or 0)}"
                else:
                    score_text = f"{(cp or 0) / 100:+.2f}"
                results.append({
                    "uci": pv[0].uci(),
                    "score": score_text,
                    "score": str(cp if cp is not None else 0),
                    "pv": " ".join(self._board.variation_san(pv[:8])),
                })
            if not results:
                return
            self.candidate_moves.emit(json.dumps(results))
            first = results[0]
            self.best_move.emit(first["uci"], first["score"], first["pv"])
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
