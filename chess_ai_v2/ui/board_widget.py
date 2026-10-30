from __future__ import annotations

import chess
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget


PIECES = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


class BoardWidget(QWidget):
    position_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False
        self.selected: chess.Square | None = None
        self.targets: set[chess.Square] = set()
        self.best_move: chess.Move | None = None
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(520, 520)

    def square_at(self, point: QPointF) -> chess.Square | None:
        side = min(self.width(), self.height())
        x0, y0 = (self.width() - side) / 2, (self.height() - side) / 2
        cell = side / 8
        col, row = int((point.x() - x0) // cell), int((point.y() - y0) // cell)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        file_, rank = (7 - col, row) if self.flipped else (col, 7 - row)
        return chess.square(file_, rank)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        square = self.square_at(event.position())
        if square is None:
            return
        piece = self.board.piece_at(square)
        if self.selected is not None and square in self.targets:
            move = chess.Move(self.selected, square)
            if self.board.piece_at(self.selected) and self.board.piece_at(self.selected).piece_type == chess.PAWN and chess.square_rank(square) in (0, 7):
                move = chess.Move(self.selected, square, promotion=chess.QUEEN)
            if move in self.board.legal_moves:
                self.board.push(move)
                self._clear_selection()
                self.position_changed.emit(self.board.fen())
                self.update()
                return
        if piece and piece.color == self.board.turn:
            self.selected = square
            self.targets = {m.to_square for m in self.board.legal_moves if m.from_square == square}
        else:
            self._clear_selection()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.selected is None:
            return
        target = self.square_at(event.position())
        if target is not None and target in self.targets:
            piece = self.board.piece_at(self.selected)
            move = chess.Move(self.selected, target)
            if piece and piece.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7):
                move = chess.Move(self.selected, target, promotion=chess.QUEEN)
            if move in self.board.legal_moves:
                self.board.push(move)
                self.position_changed.emit(self.board.fen())
        self._clear_selection()
        self.update()

    def _clear_selection(self) -> None:
        self.selected = None
        self.targets.clear()

    def set_best_move(self, uci: str) -> None:
        try:
            self.best_move = chess.Move.from_uci(uci)
        except ValueError:
            self.best_move = None
        self.update()

    def reset(self) -> None:
        self.board.reset()
        self.best_move = None
        self._clear_selection()
        self.position_changed.emit(self.board.fen())
        self.update()

    def undo(self) -> None:
        if self.board.move_stack:
            self.board.pop()
            self.best_move = None
            self._clear_selection()
            self.position_changed.emit(self.board.fen())
            self.update()

    def flip(self) -> None:
        self.flipped = not self.flipped
        self.update()

    def _center(self, square: chess.Square, x0: float, y0: float, cell: float) -> QPointF:
        file_, rank = chess.square_file(square), chess.square_rank(square)
        col, row = (7-file_, rank) if self.flipped else (file_, 7-rank)
        return QPointF(x0 + (col + 0.5) * cell, y0 + (row + 0.5) * cell)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        x0, y0 = (self.width() - side) / 2, (self.height() - side) / 2
        cell = side / 8
        light, dark = QColor("#F1F1F1"), QColor("#55585F")
        for row in range(8):
            for col in range(8):
                square = chess.square((7-col if self.flipped else col), (row if self.flipped else 7-row))
                rect = QRectF(x0 + col*cell, y0 + row*cell, cell, cell)
                painter.fillRect(rect, light if (row + col) % 2 == 0 else dark)
                if self.selected == square:
                    painter.fillRect(rect, QColor(246, 246, 105, 150))
                if square in self.targets:
                    painter.setBrush(QColor(20, 20, 20, 85))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(rect.center(), cell*0.13, cell*0.13)
                piece = self.board.piece_at(square)
                if piece:
                    glyph = PIECES[piece.symbol()]
                    painter.setFont(QFont("Segoe UI Symbol", int(cell*0.72)))
                    painter.setPen(QColor("#FFFFFF" if piece.color else "#202020"))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
        if self.best_move:
            for sq in (self.best_move.from_square, self.best_move.to_square):
                file_, rank = chess.square_file(sq), chess.square_rank(sq)
                col, row = (7-file_, rank) if self.flipped else (file_, 7-rank)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#E5B93F"), max(2, int(cell*0.045))))
                painter.drawRect(QRectF(x0 + col*cell+2, y0 + row*cell+2, cell-4, cell-4))
            a, b = self._center(self.best_move.from_square, x0, y0, cell), self._center(self.best_move.to_square, x0, y0, cell)
            painter.setPen(QPen(QColor("#E5B93F"), max(3, int(cell*0.055)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(a, b)
