from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, Signal, QPoint, QRect
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
    mirrored_click = Signal(int, int, bool)
    region_selected = Signal(int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(420, 520)
        self.resize(760, 980)
        self._transparent_mode = False
        self._hotkey_id = 41
        self._best_move_hotkey_id = 42
        self._hotkey_registered = False
        self._best_move_hotkey_registered = False
        self._mouse_listener = None
        self._selection_listener = None
        self._selection_start = None
        self._calibrated_region = None
        self._external_drag_start = None
        self.mirrored_click.connect(self._handle_mirrored_click)
        self.region_selected.connect(self._apply_selected_region)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #17191f; color: #e9ebf0; font-family: Segoe UI; }
            QPushButton { background: #292d36; border: 1px solid #3b414d; border-radius: 7px; padding: 7px 12px; }
            QPushButton:hover { background: #383e4a; }
            QLineEdit, QSpinBox, QKeySequenceEdit { background: #222630; border: 1px solid #3b414d; border-radius: 6px; padding: 6px; }
            QSlider::groove:horizontal { height: 5px; background: #424956; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e5b93f; width: 13px; margin: -5px 0; border-radius: 6px; }
        """)

        root = QWidget()
        root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root.setStyleSheet("background: transparent;")
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
        self.board_area.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.board_area.setStyleSheet("background: transparent;")
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

        self.size_row_widget = QWidget()
        size_row = QHBoxLayout(self.size_row_widget)
        size_row.addWidget(QLabel("Max. Brettgröße"))
        self.board_size_value = QLabel("520 px")
        self.board_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.board_size_slider.setRange(160, 1000)
        self.board_size_slider.setValue(520)
        self.board_size_slider.valueChanged.connect(self._fit_board)
        size_row.addWidget(self.board_size_slider, 1)
        size_row.addWidget(self.board_size_value)
        layout.addWidget(self.size_row_widget)

        self.mode_controls_widget = QWidget()
        mode_controls = QHBoxLayout(self.mode_controls_widget)
        self.free_move_check = QCheckBox("Freies Bewegen (jede Figur auf jedes Feld)")
        self.free_move_check.toggled.connect(self.board.set_free_move_mode)
        mode_controls.addWidget(self.free_move_check)
        mode_controls.addStretch()
        layout.addWidget(self.mode_controls_widget)

        self.controls_widget = QWidget()
        controls = QHBoxLayout(self.controls_widget)
        for label, callback in (("↶", self.board.undo), ("Reset", self.board.reset), ("Flip", self.board.flip)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addWidget(self.controls_widget)

        self.best_label = QLabel("Bester Zug: –")
        self.best_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self.best_label)
        self.pv_label = QLabel("Warte auf Engine-Analyse …")
        self.pv_label.setWordWrap(True)
        self.pv_label.setStyleSheet("color: #aab1bd;")
        layout.addWidget(self.pv_label)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Brett-Sichtbarkeit"))
        self.opacity_value = QLabel("100 %")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        self.board.set_visual_opacity(100)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        self.opacity_row_widget = QWidget()
        self.opacity_row_widget.setLayout(opacity_row)
        layout.addWidget(self.opacity_row_widget)

        mode_row = QHBoxLayout()
        self.pass_through = QCheckBox("Trainingsmodus: Klicks durchlassen und spiegeln")
        self.pass_through.toggled.connect(self._set_transparent_mode)
        mode_row.addWidget(self.pass_through)
        mode_row.addStretch()
        self.mode_row_widget = QWidget()
        self.mode_row_widget.setLayout(mode_row)
        layout.addWidget(self.mode_row_widget)

        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(QLabel("Hotkey für Modus"))
        self.hotkey_edit = QKeySequenceEdit(QKeySequence("F8"))
        self.hotkey_edit.setMaximumWidth(170)
        hotkey_row.addWidget(self.hotkey_edit)
        self.hotkey_button = QPushButton("Hotkey übernehmen")
        self.hotkey_button.clicked.connect(self._register_configured_hotkey)
        hotkey_row.addWidget(self.hotkey_button)
        self.hotkey_row_widget = QWidget()
        self.hotkey_row_widget.setLayout(hotkey_row)
        layout.addWidget(self.hotkey_row_widget)

        best_hotkey_row = QHBoxLayout()
        best_hotkey_row.addWidget(QLabel("Hotkey: besten Zug ausführen"))
        self.best_move_hotkey_edit = QKeySequenceEdit(QKeySequence("F9"))
        self.best_move_hotkey_edit.setMaximumWidth(170)
        best_hotkey_row.addWidget(self.best_move_hotkey_edit)
        self.best_move_hotkey_button = QPushButton("Hotkey übernehmen")
        self.best_move_hotkey_button.clicked.connect(self._register_best_move_hotkey)
        best_hotkey_row.addWidget(self.best_move_hotkey_button)
        self.best_hotkey_row_widget = QWidget()
        self.best_hotkey_row_widget.setLayout(best_hotkey_row)
        layout.addWidget(self.best_hotkey_row_widget)

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
        self.engine_row_widget = QWidget()
        self.engine_row_widget.setLayout(engine_row)
        layout.addWidget(self.engine_row_widget)

        self.region_button = QPushButton("Spielfeldbereich auswählen")
        self.region_button.clicked.connect(self._start_region_selection)
        layout.addWidget(self.region_button)

        self.board.position_changed.connect(self.engine_position.emit)
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None
        self._register_configured_hotkey()
        self._register_best_move_hotkey()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_board()

    def _fit_board(self, _value: int = 0) -> None:
        if not hasattr(self, "board"):
            return
        area = self.board_area.contentsRect()
        available = max(80, min(area.width(), area.height()))
        if self._calibrated_region is not None:
            self.board.setFixedSize(available, available)
        else:
            size = min(self.board_size_slider.value(), available)
            self.board.setFixedSize(size, size)
            self.board_size_value.setText(f"{size} px")

    def _start_region_selection(self) -> None:
        if sys.platform != "win32":
            self.status.setText("Bereichsauswahl benötigt Windows.")
            return
        try:
            from pynput import mouse
            self._selection_start = None
            self.hide()
            self.status.setText("Ziehe einen Rahmen um das Schachbrett.")
            def on_click(x, y, button, pressed):
                if button != mouse.Button.left:
                    return
                if pressed:
                    self._selection_start = (int(x), int(y))
                elif self._selection_start is not None:
                    x0, y0 = self._selection_start
                    x1, y1 = int(x), int(y)
                    self._selection_listener.stop()
                    self.region_selected.emit(min(x0, x1), min(y0, y1), abs(x1-x0), abs(y1-y0))
                    return False
            self._selection_listener = mouse.Listener(on_click=on_click)
            self._selection_listener.start()
        except Exception as exc:
            self.show()
            self.status.setText(f"Bereichsauswahl fehlgeschlagen: {exc}")

    def _apply_selected_region(self, x: int, y: int, width: int, height: int) -> None:
        if width < 80 or height < 80 or abs(width-height) > max(width, height) * 0.12:
            self.show()
            self.status.setText("Bitte möglichst genau das quadratische Schachbrett markieren.")
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        rect = QRect(round(x/dpr), round(y/dpr), round(width/dpr), round(height/dpr))
        self._calibrated_region = rect
        for widget in (self.size_row_widget, self.mode_controls_widget, self.controls_widget,
                       self.best_label, self.pv_label, self.opacity_row_widget, self.mode_row_widget,
                       self.hotkey_row_widget, self.best_hotkey_row_widget, self.engine_row_widget,
                       self.region_button):
            widget.hide()
        self.board.setMinimumSize(80, 80)
        self.board.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(80, 80)
        self.setMaximumSize(4096, 4096)
        self.setGeometry(rect)
        self.show()
        self.raise_()
        self.status.setText("Spielfeldbereich übernommen. Einstellungen über erneute Bereichsauswahl/Zurücksetzen verfügbar.")

    def _set_opacity(self, value: int) -> None:
        self.board.set_visual_opacity(value)
        self.opacity_value.setText(f"{value} %")

    def _set_transparent_mode(self, enabled: bool) -> None:
        self._transparent_mode = enabled
        if sys.platform != "win32":
            self.status.setText("Der Trainingsmodus benötigt Windows.")
            self.pass_through.blockSignals(True)
            self.pass_through.setChecked(False)
            self.pass_through.blockSignals(False)
            self._transparent_mode = False
            return

        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        get_style = ctypes.windll.user32.GetWindowLongPtrW
        set_style = ctypes.windll.user32.SetWindowLongPtrW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        style = get_style(hwnd, GWL_EXSTYLE)
        if enabled:
            set_style(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 150, 0x00000002)
            try:
                from pynput import mouse
                def on_click(x, y, button, pressed):
                    if button == mouse.Button.left:
                        self.mirrored_click.emit(int(x), int(y), bool(pressed))
                self._mouse_listener = mouse.Listener(on_click=on_click)
                self._mouse_listener.start()
                self.status.setText("Trainingsmodus AN: Klicks werden gespiegelt. F8 beendet den Modus.")
            except Exception as exc:
                set_style(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
                self._transparent_mode = False
                self.pass_through.blockSignals(True)
                self.pass_through.setChecked(False)
                self.pass_through.blockSignals(False)
                self.status.setText(f"Mauseingabe konnte nicht gestartet werden: {exc}")
        else:
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x00000002)
            set_style(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
            if self._mouse_listener is not None:
                self._mouse_listener.stop()
                self._mouse_listener = None
            self.status.setText("Trainingsmodus AUS: Chess AI V2 direkt bedienen.")

    def _handle_mirrored_click(self, screen_x: int, screen_y: int, pressed: bool) -> None:
        """Mirror the physical mouse down/up onto our board while Windows passes it through."""
        if not self._transparent_mode:
            return

        # pynput reports physical screen pixels on Windows, while Qt widget
        # coordinates are device-independent pixels. Convert for scaled displays.
        dpr = float(self.devicePixelRatioF() or 1.0)
        qt_x = round(screen_x / dpr)
        qt_y = round(screen_y / dpr)
        origin = self.board.mapToGlobal(QPoint(0, 0))
        local = QPoint(qt_x - origin.x(), qt_y - origin.y())
        square = self.board.square_at(local)

        if pressed:
            self._external_drag_start = square
            if square is not None:
                self.board.apply_external_click(square)
            return

        start = self._external_drag_start
        self._external_drag_start = None
        if start is None or square is None:
            return
        if start != square:
            # A drag is one down/up pair; apply the destination to the
            # selection created on mouse-down.
            self.board.apply_external_click(square)

    def _hotkey_parts(self, sequence: QKeySequence):
        if sequence.isEmpty() or sequence.count() != 1:
            return None
        key = int(sequence[0].toCombined())
        modifiers = 0
        if key & Qt.KeyboardModifier.AltModifier.value:
            modifiers |= 0x0001
        if key & Qt.KeyboardModifier.ControlModifier.value:
            modifiers |= 0x0002
        if key & Qt.KeyboardModifier.ShiftModifier.value:
            modifiers |= 0x0004
        if key & Qt.KeyboardModifier.MetaModifier.value:
            modifiers |= 0x0008
        qt_key = key & 0x01FFFFFF
        if Qt.Key.Key_F1.value <= qt_key <= Qt.Key.Key_F24.value:
            vk = 0x70 + (qt_key - Qt.Key.Key_F1.value)
        else:
            vk = qt_key
        return modifiers, vk

    def _register_best_move_hotkey(self) -> None:
        if sys.platform != "win32":
            return
        parts = self._hotkey_parts(self.best_move_hotkey_edit.keySequence())
        if parts is None:
            self.status.setText("Bitte genau eine Tastenkombination für den besten Zug festlegen.")
            return
        if self._best_move_hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._best_move_hotkey_id)
            self._best_move_hotkey_registered = False
        if ctypes.windll.user32.RegisterHotKey(int(self.winId()), self._best_move_hotkey_id, *parts):
            self._best_move_hotkey_registered = True
            self.status.setText("Hotkey für besten Zug gesetzt.")
        else:
            self.status.setText("Hotkey für besten Zug ist belegt oder ungültig.")

    def _execute_best_move(self) -> None:
        if self.board.play_best_move():
            self.status.setText("Bester Zug wurde auf dem Overlay-Brett ausgeführt.")
        else:
            self.status.setText("Kein legaler bester Zug verfügbar. Erst Stockfish starten/Analyse abwarten.")

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
        if key & Qt.KeyboardModifier.AltModifier.value:
            modifiers |= 0x0001
        if key & Qt.KeyboardModifier.ControlModifier.value:
            modifiers |= 0x0002
        if key & Qt.KeyboardModifier.ShiftModifier.value:
            modifiers |= 0x0004
        if key & Qt.KeyboardModifier.MetaModifier.value:
            modifiers |= 0x0008
        qt_key = key & 0x01FFFFFF
        # Qt encodes function keys as 0x01000030+n; Win32 uses VK_F1..VK_F24.
        if Qt.Key.Key_F1.value <= qt_key <= Qt.Key.Key_F24.value:
            vk = 0x70 + (qt_key - Qt.Key.Key_F1.value)
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
                if msg.message == 0x0312 and msg.wParam == self._best_move_hotkey_id:
                    self._execute_best_move()
                    return True, 0
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
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if sys.platform == "win32":
            if self._hotkey_registered:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._hotkey_id)
            if self._best_move_hotkey_registered:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._best_move_hotkey_id)
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
