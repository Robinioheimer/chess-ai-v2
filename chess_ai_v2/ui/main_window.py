from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, Signal, QPoint
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QLineEdit, QSpinBox, QCheckBox, QFileDialog, QKeySequenceEdit,
    QSizePolicy
)

from chess_ai_v2.ui.board_widget import BoardWidget
from chess_ai_v2.engine.worker import EngineWorker


class MainWindow(QMainWindow):
    engine_position = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(420, 520)
        self.resize(760, 980)
        self._transparent_mode = False
        self._hotkey_id = 41
        self._hotkey_registered = False

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #17191f; color: #e9ebf0; font-family: Segoe UI; }
            QPushButton { background: #292d36; border: 1px solid #3b414d; border-radius: 7px; padding: 7px 12px; }
            QPushButton:hover { background: #383e4a; }
            QLineEdit, QSpinBox, QKeySequenceEdit { background: #222630; border: 1px solid #3b414d; border-radius: 6px; padding: 6px; }
            QSlider::groove:horizontal { height: 5px; background: #424956; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e5b93f; width: 13px; margin: -5px 0; border-radius: 6px; }
        """)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("CHESS AI <b>V2</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 17px; letter-spacing: 1px;")
        self.status = QLabel("Engine nicht verbunden")
        self.status.setStyleSheet("color: #aab1bd;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        layout.addLayout(header)

        self.board_area = QWidget()
        self.board_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        board_layout = QHBoxLayout(self.board_area)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.addStretch(1)
        self.board = BoardWidget()
        self.board.setMinimumSize(160, 160)
        self.board.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        board_layout.addWidget(self.board, 0, Qt.AlignmentFlag.AlignCenter)
        board_layout.addStretch(1)
        layout.addWidget(self.board_area, 1)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Max. Brettgröße"))
        self.board_size_value = QLabel("520 px")
        self.board_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.board_size_slider.setRange(160, 1000)
        self.board_size_slider.setValue(520)
        self.board_size_slider.valueChanged.connect(self._fit_board)
        size_row.addWidget(self.board_size_slider, 1)
        size_row.addWidget(self.board_size_value)
        layout.addLayout(size_row)

        controls = QHBoxLayout()
        for label, callback in (("↶", self.board.undo), ("Reset", self.board.reset), ("Flip", self.board.flip)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

        self.best_label = QLabel("Bester Zug: –")
        self.best_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self.best_label)
        self.pv_label = QLabel("Warte auf Engine-Analyse …")
        self.pv_label.setWordWrap(True)
        self.pv_label.setStyleSheet("color: #aab1bd;")
        layout.addWidget(self.pv_label)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Fenster-Deckkraft"))
        self.opacity_value = QLabel("100 %")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)

        mode_row = QHBoxLayout()
        self.pass_through = QCheckBox("Transparenzmodus: durch leere Flächen klicken")
        self.pass_through.toggled.connect(self._set_transparent_mode)
        mode_row.addWidget(self.pass_through)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(QLabel("Hotkey für Modus"))
        self.hotkey_edit = QKeySequenceEdit(QKeySequence("F8"))
        self.hotkey_edit.setMaximumWidth(170)
        hotkey_row.addWidget(self.hotkey_edit)
        self.hotkey_button = QPushButton("Hotkey übernehmen")
        self.hotkey_button.clicked.connect(self._register_configured_hotkey)
        hotkey_row.addWidget(self.hotkey_button)
        layout.addLayout(hotkey_row)

        engine_row = QHBoxLayout()
        self.path_edit = QLineEdit(os.environ.get("STOCKFISH_PATH", ""))
        self.path_edit.setPlaceholderText("Pfad zur Stockfish.exe")
        self.browse_button = QPushButton("Durchsuchen …")
        self.browse_button.clicked.connect(self._browse_stockfish)
        self.depth = QSpinBox()
        self.depth.setRange(5, 30)
        self.depth.setValue(15)
        self.start_button = QPushButton("Stockfish starten")
        self.start_button.clicked.connect(self._start_engine)
        engine_row.addWidget(self.path_edit, 1)
        engine_row.addWidget(self.browse_button)
        engine_row.addWidget(QLabel("Tiefe"))
        engine_row.addWidget(self.depth)
        engine_row.addWidget(self.start_button)
        layout.addLayout(engine_row)

        self.board.position_changed.connect(self.engine_position.emit)
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None
        self._register_configured_hotkey()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_board()

    def _fit_board(self, _value: int = 0) -> None:
        if not hasattr(self, "board"):
            return
        area = self.board_area.contentsRect()
        available = max(160, min(area.width(), area.height()))
        size = min(self.board_size_slider.value(), available)
        self.board.setFixedSize(size, size)
        self.board_size_value.setText(f"{size} px")

    def _set_opacity(self, value: int) -> None:
        self.setWindowOpacity(value / 100)
        self.opacity_value.setText(f"{value} %")

    def _set_transparent_mode(self, enabled: bool) -> None:
        self._transparent_mode = enabled
        if sys.platform != "win32":
            self.status.setText("Der Klick-durch-Modus benötigt Windows.")
            self.pass_through.blockSignals(True)
            self.pass_through.setChecked(False)
            self.pass_through.blockSignals(False)
            self._transparent_mode = False
            return
        self.status.setText(
            "Modus AN: leere Felder lassen Klicks durch; Figuren bleiben greifbar"
            if enabled else "Modus AUS: das ganze Brett ist bedienbar"
        )
        self.winId()

    def _register_configured_hotkey(self) -> None:
        if sys.platform != "win32":
            self.status.setText("Globale Hotkeys sind nur unter Windows verfügbar.")
            return
        sequence = self.hotkey_edit.keySequence()
        if sequence.isEmpty() or sequence.count() != 1:
            self.status.setText("Bitte genau eine Tastenkombination festlegen.")
            return
        # In Qt 6, QKeySequence[i] returns QKeyCombination, not an int.
        key = int(sequence[0].toCombined())
        modifiers = 0
        if key & int(Qt.KeyboardModifier.AltModifier):
            modifiers |= 0x0001
        if key & int(Qt.KeyboardModifier.ControlModifier):
            modifiers |= 0x0002
        if key & int(Qt.KeyboardModifier.ShiftModifier):
            modifiers |= 0x0004
        if key & int(Qt.KeyboardModifier.MetaModifier):
            modifiers |= 0x0008
        qt_key = key & 0x01FFFFFF
        # Qt encodes function keys as 0x01000030+n; Win32 uses VK_F1..VK_F24.
        if int(Qt.Key.Key_F1) <= qt_key <= int(Qt.Key.Key_F24):
            vk = 0x70 + (qt_key - int(Qt.Key.Key_F1))
        else:
            vk = qt_key
        if self._hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._hotkey_id)
            self._hotkey_registered = False
        if ctypes.windll.user32.RegisterHotKey(int(self.winId()), self._hotkey_id, modifiers, vk):
            self._hotkey_registered = True
            self.status.setText("Hotkey gesetzt: " + sequence.toString(QKeySequence.SequenceFormat.NativeText))
        else:
            self.status.setText("Hotkey belegt oder ungültig – bitte eine andere Kombination wählen.")

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == 0x0312 and msg.wParam == self._hotkey_id:
                    self.pass_through.setChecked(not self.pass_through.isChecked())
                    return True, 0
                if msg.message == 0x0084 and self._transparent_mode:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    local = self.board.mapFromGlobal(QPoint(x, y))
                    square = self.board.square_at(local)
                    if square is not None and self.board.piece_at_visual_hit(local, square):
                        return True, 1  # HTCLIENT: pieces still receive mouse input
                    return True, -1  # HTTRANSPARENT: empty squares pass through
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _browse_stockfish(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Stockfish-Programm auswählen",
            os.path.dirname(self.path_edit.text().strip()) or os.path.expanduser("~"),
            "Stockfish (stockfish.exe);;Programme (*.exe);;Alle Dateien (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _start_engine(self) -> None:
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = EngineWorker(self.path_edit.text().strip(), self.depth.value())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self.engine_position.connect(self._worker.set_position)
        self._worker.status.connect(self.status.setText)
        self._worker.failed.connect(self.status.setText)
        self._worker.best_move.connect(self._on_best_move)
        self._thread.start()
        self.start_button.setEnabled(False)

    def _on_best_move(self, uci: str, score: str, pv: str) -> None:
        self.board.set_best_move(uci)
        try:
            move = self.board.board.parse_uci(uci)
            san = self.board.board.san(move)
        except ValueError:
            san = uci
        self.best_label.setText(f"Bester Zug: {san}  ·  Bewertung: {score}")
        self.pv_label.setText(f"Variantenfolge: {pv}")

    def closeEvent(self, event) -> None:
        if self._hotkey_registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._hotkey_id)
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
