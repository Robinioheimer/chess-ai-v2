from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QLineEdit, QSpinBox, QCheckBox, QFileDialog, QFrame
)
from chess_ai_v2.ui.board_widget import BoardWidget
from chess_ai_v2.engine.worker import EngineWorker


class MainWindow(QMainWindow):
    engine_position = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(560, 760)
        self.resize(760, 980)
        self.setWindowOpacity(0.96)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #17191f; color: #e9ebf0; font-family: Segoe UI; }
            QPushButton { background: #292d36; border: 1px solid #3b414d; border-radius: 7px; padding: 7px 12px; }
            QPushButton:hover { background: #383e4a; }
            QLineEdit, QSpinBox { background: #222630; border: 1px solid #3b414d; border-radius: 6px; padding: 6px; }
            QSlider::groove:horizontal { height: 5px; background: #424956; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e5b93f; width: 13px; margin: -5px 0; border-radius: 6px; }
        """)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

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

        board_area = QWidget()
        board_area_layout = QHBoxLayout(board_area)
        board_area_layout.setContentsMargins(0, 0, 0, 0)
        board_area_layout.addStretch()
        self.board = BoardWidget()
        self.board.setFixedSize(520, 520)
        board_area_layout.addWidget(self.board, 0, Qt.AlignmentFlag.AlignCenter)
        board_area_layout.addStretch()
        layout.addWidget(board_area, 1)

        board_size_row = QHBoxLayout()
        board_size_row.addWidget(QLabel("Brettgröße"))
        self.board_size_value = QLabel("520 px")
        self.board_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.board_size_slider.setRange(320, 680)
        self.board_size_slider.setSingleStep(20)
        self.board_size_slider.setPageStep(40)
        self.board_size_slider.setValue(520)
        self.board_size_slider.valueChanged.connect(self._set_board_size)
        board_size_row.addWidget(self.board_size_slider, 1)
        board_size_row.addWidget(self.board_size_value)
        layout.addLayout(board_size_row)

        controls = QHBoxLayout()
        for label, callback in (("↶", self.board.undo), ("Reset", self.board.reset), ("Flip", self.board.flip)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

        analysis = QHBoxLayout()
        self.best_label = QLabel("Bester Zug: –")
        self.best_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        analysis.addWidget(self.best_label)
        layout.addLayout(analysis)
        self.pv_label = QLabel("Warte auf Engine-Analyse …")
        self.pv_label.setWordWrap(True)
        self.pv_label.setStyleSheet("color: #aab1bd;")
        layout.addWidget(self.pv_label)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Transparenz"))
        self.opacity_value = QLabel("96 %")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(96)
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)

        passthrough_row = QHBoxLayout()
        self.pass_through = QCheckBox("Maus durchlassen (Brett nicht bedienbar)")
        self.pass_through.toggled.connect(self._set_mouse_passthrough)
        passthrough_row.addWidget(self.pass_through)
        passthrough_row.addStretch()
        layout.addLayout(passthrough_row)

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
        self._hotkey_registered = False
        if sys.platform == "win32":
            # F8 remains available even while mouse input is passed through.
            try:
                self._hotkey_registered = bool(
                    ctypes.windll.user32.RegisterHotKey(int(self.winId()), 1, 0, 0x77)
                )
            except Exception:
                self._hotkey_registered = False
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None

    def _set_opacity(self, value: int) -> None:
        self.setWindowOpacity(max(0.05, value / 100))
        self.opacity_value.setText(f"{value} %")

    def _set_board_size(self, value: int) -> None:
        self.board.setFixedSize(value, value)
        self.board_size_value.setText(f"{value} px")

    def _set_mouse_passthrough(self, enabled: bool) -> None:
        if sys.platform != "win32":
            self.status.setText("Maus-Durchlassen ist nur unter Windows verfügbar")
            self.pass_through.blockSignals(True)
            self.pass_through.setChecked(False)
            self.pass_through.blockSignals(False)
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.restype = ctypes.c_longlong
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_style.restype = ctypes.c_longlong
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
            ex_style = get_style(hwnd, -20)  # GWL_EXSTYLE
            WS_EX_TRANSPARENT = 0x00000020
            if enabled:
                ex_style |= WS_EX_TRANSPARENT
                self.status.setText("Maus wird an das Fenster dahinter weitergegeben")
            else:
                ex_style &= ~WS_EX_TRANSPARENT
                self.status.setText("Brett wieder interaktiv")
            set_style(hwnd, -20, ex_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception as exc:
            self.status.setText(f"Windows-Mausmodus fehlgeschlagen: {exc}")
            self.pass_through.blockSignals(True)
            self.pass_through.setChecked(False)
            self.pass_through.blockSignals(False)

    def _browse_stockfish(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Stockfish-Programm auswählen",
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

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == 0x0312 and msg.wParam == 1:  # WM_HOTKEY, our F8 id
                    self.pass_through.setChecked(not self.pass_through.isChecked())
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        if self._hotkey_registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), 1)
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
