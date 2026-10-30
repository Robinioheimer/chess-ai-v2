from __future__ import annotations

import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QLineEdit, QSpinBox, QFrame
)
from chess_ai_v2.ui.board_widget import BoardWidget
from chess_ai_v2.engine.worker import EngineWorker


class MainWindow(QMainWindow):
    engine_position = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(390, 500)
        self.resize(620, 760)
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

        self.board = BoardWidget()
        layout.addWidget(self.board, 1)

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

        engine_row = QHBoxLayout()
        self.path_edit = QLineEdit(os.environ.get("STOCKFISH_PATH", ""))
        self.path_edit.setPlaceholderText("Pfad zur Stockfish.exe")
        self.depth = QSpinBox()
        self.depth.setRange(5, 30)
        self.depth.setValue(15)
        self.start_button = QPushButton("Stockfish starten")
        self.start_button.clicked.connect(self._start_engine)
        engine_row.addWidget(self.path_edit, 1)
        engine_row.addWidget(QLabel("Tiefe"))
        engine_row.addWidget(self.depth)
        engine_row.addWidget(self.start_button)
        layout.addLayout(engine_row)

        self.board.position_changed.connect(self.engine_position.emit)
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None

    def _set_opacity(self, value: int) -> None:
        self.setWindowOpacity(max(0.05, value / 100))
        self.opacity_value.setText(f"{value} %")

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
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
