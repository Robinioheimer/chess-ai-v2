from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, Signal, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QLineEdit, QSpinBox, QCheckBox, QFileDialog, QKeySequenceEdit,
    QSizePolicy, QScrollArea
)

from chess_ai_v2.ui.board_widget import BoardWidget
from chess_ai_v2.engine.worker import EngineWorker


class RegionSelectionOverlay(QWidget):
    selection_done = Signal(QRect)

    def __init__(self, screen_geometry: QRect) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.start = None
        self.current = None
        self.show()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 145))
        if self.current is not None:
            rect = QRect(self.start, self.current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#e5b93f"), 3))
            painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.current = self.start
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start is not None:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.start is None:
            return
        end = event.position().toPoint()
        local = QRect(self.start, end).normalized()
        global_rect = local.translated(self.geometry().topLeft())
        self.selection_done.emit(global_rect)
        self.close()


class BoardPopup(QMainWindow):
    def __init__(self, board: BoardWidget, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chess AI V2 – Schachbrett")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: 0px;")
        self.resize(560, 560)
        board.setParent(self)
        board.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        board.setAutoFillBackground(False)
        board.setStyleSheet("background: transparent; border: 0px;")
        board.setMinimumSize(160, 160)
        board.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(board)
        self.board = board


class MainWindow(QMainWindow):
    engine_position = Signal(str)
    mirrored_click = Signal(int, int, bool)
    region_selected = Signal(int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        # The settings window adapts to the actual usable monitor area.
        # Its contents remain inside the scroll area, even on short displays.
        self.setMinimumSize(340, 280)
        self._transparent_mode = False
        self._hotkey_id = 41
        self._best_move_hotkey_id = 42
        self._popup_hotkey_id = 43
        self._hotkey_registered = False
        self._best_move_hotkey_registered = False
        self._popup_hotkey_registered = False
        self._mouse_listener = None
        self._selection_listener = None
        self._selection_overlay = None
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
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.settings_content = QWidget()
        self.settings_scroll.setWidget(self.settings_content)
        root_layout.addWidget(self.settings_scroll)
        layout = QVBoxLayout(self.settings_content)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(9)

        self.header_widget = QWidget()
        header = QHBoxLayout(self.header_widget)
        title = QLabel("CHESS AI <b>V2</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 17px; letter-spacing: 1px;")
        self.status = QLabel("Engine nicht verbunden")
        self.status.setStyleSheet("color: #aab1bd;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        layout.addWidget(self.header_widget)

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
        layout.addWidget(self.board_area)
        self.board_area.hide()
        self.board_popup = BoardPopup(self.board, self)
        self.board_toggle_button = QPushButton("Spielfeld anzeigen")
        self.board_toggle_button.clicked.connect(self._toggle_board_visibility)
        layout.addWidget(self.board_toggle_button)

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
        # Board controls stay in the scrollable settings window, not in the popup.
        self.best_label = QLabel("Bester Zug: –")
        self.pv_label = QLabel("Warte auf Engine-Analyse …")

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

        self.region_button = QPushButton("Spielfeldgröße mit Maus markieren")
        self.region_button.clicked.connect(self._start_region_selection)
        layout.addWidget(self.region_button)

        self.board.position_changed.connect(self.engine_position.emit)
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None
        self._register_configured_hotkey()
        self._register_best_move_hotkey()
        self._register_popup_hotkey()

        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(620, max(340, available.width() - 32))
            height = min(760, max(280, available.height() - 32))
            self.resize(width, height)
            self.move(
                available.x() + (available.width() - width) // 2,
                available.y() + (available.height() - height) // 2,
            )
        else:
            self.resize(560, 680)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_board()

    def _fit_board(self, _value: int = 0) -> None:
        if not hasattr(self, "board"):
            return
        area = self.board_area.contentsRect()
        available = max(80, min(area.width(), area.height()))
        if self._calibrated_region is not None:
            size = min(available, self._calibrated_region.width(), self._calibrated_region.height())
            self.board.setFixedSize(max(80, size), max(80, size))
        else:
            size = min(self.board_size_slider.value(), available)
            self.board.setFixedSize(size, size)
            self.board_size_value.setText(f"{size} px")

    def _start_region_selection(self) -> None:
        if sys.platform != "win32":
            self.status.setText("Bereichsauswahl benötigt Windows.")
            return
        screen = self.screen()
        if screen is None:
            self.status.setText("Kein Bildschirm für die Bereichsauswahl gefunden.")
            return
        self.hide()
        self._selection_overlay = RegionSelectionOverlay(screen.geometry())
        self._selection_overlay.selection_done.connect(
            lambda rect: self.region_selected.emit(rect.x(), rect.y(), rect.width(), rect.height())
        )
        self._selection_overlay.destroyed.connect(lambda: self.show())

    def _apply_selected_region(self, x: int, y: int, width: int, height: int) -> None:
        if width < 80 or height < 80 or abs(width-height) > max(width, height) * 0.12:
            self.show()
            self.status.setText("Bitte möglichst genau das quadratische Schachbrett markieren.")
            return
        # RegionSelectionOverlay reports Qt global logical coordinates.
        # Keep those coordinates in the same Qt coordinate system; do not
        # multiply/divide by monitor DPI (that caused scaling and offsets).
        selected = QRect(x, y, width, height)
        size = min(selected.width(), selected.height())

        # A chessboard must be square. Fit the largest square centered inside
        # the selection, never larger than the selected area.
        left = selected.x() + (selected.width() - size) // 2
        top = selected.y() + (selected.height() - size) // 2
        rect = QRect(left, top, size, size)
        self._calibrated_region = rect

        target_screen = QApplication.screenAt(rect.center())
        if target_screen is not None and self.board_popup.windowHandle() is not None:
            self.board_popup.windowHandle().setScreen(target_screen)
        self.board_popup.setGeometry(rect)
        self.board.setMinimumSize(80, 80)
        self.board.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.board_popup.show()
        self.board_popup.raise_()
        self.board_popup.activateWindow()
        self.board_toggle_button.setText("Spielfeld ausblenden")
        self.show()
        self.raise_()
        self.status.setText("Bereich übernommen. Das Schachbrett wurde in einem eigenen Fenster geöffnet.")

    def _toggle_board_visibility(self) -> None:
        if self.board_popup.isVisible():
            self.board_popup.hide()
            self.board_toggle_button.setText("Spielfeld anzeigen")
        else:
            self.board_popup.show()
            self.board_popup.raise_()
            self.board_popup.activateWindow()
            self.board_toggle_button.setText("Spielfeld ausblenden")

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

        hwnd = int(self.board_popup.winId())
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


    def _register_popup_hotkey(self) -> None:
        if sys.platform != "win32":
            return
        if ctypes.windll.user32.RegisterHotKey(int(self.winId()), self._popup_hotkey_id, 0, 0x76):  # F7
            self._popup_hotkey_registered = True
        else:
            self._popup_hotkey_registered = False
            self.status.setText("F7 ist bereits belegt; Popup weiterhin über die Einstellungen steuerbar.")

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
                if msg.message == 0x0312 and msg.wParam == self._popup_hotkey_id:
                    self._toggle_board_visibility()
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
        self.board_popup.setWindowTitle(f"Chess AI V2 – {san} ({score})")

    def closeEvent(self, event) -> None:
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if sys.platform == "win32":
            if self._hotkey_registered:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._hotkey_id)
            if self._best_move_hotkey_registered:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._best_move_hotkey_id)
            if self._popup_hotkey_registered:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._popup_hotkey_id)
        if hasattr(self, "board_popup"):
            self.board_popup.close()
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
