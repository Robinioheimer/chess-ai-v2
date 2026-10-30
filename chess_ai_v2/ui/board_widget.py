from __future__ import annotations

import chess
from chess import svg as chess_svg
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QByteArray
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget


class BoardWidget(QWidget):
    position_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False
        self.selected: chess.Square | None = None
        self.targets: set[chess.Square] = set()
        self.best_move: chess.Move | None = None
        self.free_move_mode = False
        self.visual_opacity = 100
        self._piece_svg_cache: dict[str, QSvgRenderer] = {}
        self.setMinimumSize(160, 160)
        self.setMouseTracking(True)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(520, 520)

    def set_visual_opacity(self, value: int) -> None:
        self.visual_opacity = max(0, min(100, int(value)))
        self.update()

    def square_at(self, point: QPointF) -> chess.Square | None:
        side = min(self.width(), self.height())
        x0, y0 = (self.width() - side) / 2, (self.height() - side) / 2
        cell = side / 8
        col, row = int((point.x() - x0) // cell), int((point.y() - y0) // cell)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        file_, rank = (7 - col, row) if self.flipped else (col, 7 - row)
        return chess.square(file_, rank)

    def piece_at_visual_hit(self, point, square: chess.Square) -> bool:
        # Empty squares pass clicks through; an active drag keeps the mouse grab.
        return self.board.piece_at(square) is not None

    def apply_external_click(self, square: chess.Square) -> None:
        """Mirror a physical click observed outside the overlay onto this board."""
        piece = self.board.piece_at(square)
        if self.free_move_mode:
            self._free_move_click(square)
            return
        if self.selected is not None and square in self.targets:
            moving_piece = self.board.piece_at(self.selected)
            move = chess.Move(self.selected, square)
            if moving_piece and moving_piece.piece_type == chess.PAWN and chess.square_rank(square) in (0, 7):
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
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        square = self.square_at(event.position())
        if square is None:
            return
        piece = self.board.piece_at(square)
        if self.free_move_mode:
            self._free_move_click(square)
            return
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
        if self.free_move_mode:
            if target is not None:
                self._free_move_click(target)
            else:
                self._clear_selection()
                self.update()
            return
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

    def set_free_move_mode(self, enabled: bool) -> None:
        self.free_move_mode = enabled
        self._clear_selection()
        self.update()

    def _free_move_click(self, square: chess.Square) -> None:
        """Move the side-to-move piece to any square, ignoring normal piece geometry."""
        piece = self.board.piece_at(square)
        if self.selected is None:
            if piece and piece.color == self.board.turn:
                self.selected = square
                self.targets = set(chess.SQUARES)
                self.targets.discard(square)
            self.update()
            return

        source = self.selected
        moving = self.board.piece_at(source)
        self._clear_selection()
        if moving is None or source == square:
            self.update()
            return
        # Keep both kings on the board; otherwise python-chess/Stockfish cannot
        # represent a useful position. Capturing any other piece is allowed.
        if piece and piece.piece_type == chess.KING:
            self.update()
            return
        promotion = chess.QUEEN if moving.piece_type == chess.PAWN and chess.square_rank(square) in (0, 7) else None
        move = chess.Move(source, square, promotion=promotion)
        self.board.push(move)
        self.best_move = None
        self.position_changed.emit(self.board.fen())
        self.update()

    def play_best_move(self) -> bool:
        if self.best_move is None or self.free_move_mode:
            return False
        move = self.best_move
        if move not in self.board.legal_moves:
            return False
        self.board.push(move)
        self._clear_selection()
        self.best_move = None
        self.position_changed.emit(self.board.fen())
        self.update()
        return True

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
        alpha = round(255 * self.visual_opacity / 100)
        light, dark = QColor(241, 241, 241, alpha), QColor(85, 88, 95, alpha)
        for row in range(8):
            for col in range(8):
                square = chess.square((7-col if self.flipped else col), (row if self.flipped else 7-row))
                rect = QRectF(x0 + col*cell, y0 + row*cell, cell, cell)
                painter.fillRect(rect, light if (row + col) % 2 == 0 else dark)
                if self.selected == square and alpha > 0:
                    painter.fillRect(rect, QColor(246, 246, 105, round(150 * self.visual_opacity / 100)))
                if square in self.targets and alpha > 0:
                    painter.setBrush(QColor(20, 20, 20, round(85 * self.visual_opacity / 100)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(rect.center(), cell*0.13, cell*0.13)
                piece = self.board.piece_at(square)
                if piece and alpha > 0:
                    # python-chess liefert hochwertige Staunton-SVG-Figuren.
                    # Sie wirken deutlich näher an klassischen Online-Schachsets
                    # als die bisherigen Unicode-Schriftzeichen.
                    symbol = piece.symbol()
                    renderer = self._piece_svg_cache.get(symbol)
                    if renderer is None:
                        svg = chess_svg.piece(piece, size=256)
                        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
                        self._piece_svg_cache[symbol] = renderer
                    painter.save()
                    painter.setOpacity(alpha / 255.0)
                    margin = cell * 0.035
                    renderer.render(painter, rect.adjusted(margin, margin, -margin, -margin))
                    painter.restore()
        if self.best_move:
            for sq in (self.best_move.from_square, self.best_move.to_square):
                file_, rank = chess.square_file(sq), chess.square_rank(sq)
                col, row = (7-file_, rank) if self.flipped else (file_, 7-rank)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#E5B93F"), max(2, int(cell*0.045))))
                painter.drawRect(QRectF(x0 + col*cell+2, y0 + row*cell+2, cell-4, cell-4))
            a, b = self._center(self.best_move.from_square, x0, y0, cell), self._center(self.best_move.to_square, x0, y0, cell)
            # Draw a clear directional arrow, not just a line.
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length = (dx * dx + dy * dy) ** 0.5
            if length > 0:
                ux, uy = dx / length, dy / length
                head_len = cell * 0.24
                half_width = cell * 0.12
                tip = b
                base = QPointF(b.x() - ux * head_len, b.y() - uy * head_len)
                left = QPointF(base.x() - uy * half_width, base.y() + ux * half_width)
                right = QPointF(base.x() + uy * half_width, base.y() - ux * half_width)
                shaft_end = QPointF(b.x() - ux * head_len * 0.72, b.y() - uy * head_len * 0.72)
                painter.setPen(QPen(QColor("#6b4b00"), max(5, int(cell * 0.085)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(a, shaft_end)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#E5B93F"))
                painter.drawPolygon(QPolygonF([tip, left, right]))
