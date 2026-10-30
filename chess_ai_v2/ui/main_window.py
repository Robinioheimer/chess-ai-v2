from __future__ import annotations

import os
import sys
import ctypes
import json
import shutil
from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, Signal, QPoint, QRect, QSettings
from PySide6.QtGui import QPainter, QColor, QPen, QCursor
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QLineEdit, QSpinBox, QCheckBox, QFileDialog, QKeySequenceEdit,
    QSizePolicy, QScrollArea, QInputDialog
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
            # Mausposition direkt relativ zu genau diesem Monitor-Overlay.
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
        # Die globale Position ergibt sich aus dem Ursprung des Monitors plus
        # der lokalen Auswahl. Keine Umrechnung über ein virtuelles Desktop-
        # Overlay und keine zweite mapFromGlobal/mapToGlobal-Rundung.
        origin = self.geometry().topLeft()
        global_rect = QRect(origin + local.topLeft(), local.size())
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
    analysis_multipv_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.settings_store = QSettings("RobinDarian", "ChessAIV2")
        self.setWindowTitle("Chess AI V2")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        # The settings window adapts to the actual usable monitor area.
        # Its contents remain inside the scroll area, even on short displays.
        self.setMinimumSize(340, 280)
        self._transparent_mode = False
        self._hotkey_id = 41
        self._best_move_hotkey_id = 42
        self._popup_hotkey_id = 43
        self._back_hotkey_id = 44
        self._visibility_toggle_hotkey_id = 45
        self._hotkey_registered = False
        self._best_move_hotkey_registered = False
        self._popup_hotkey_registered = False
        self._back_hotkey_registered = False
        self._visibility_toggle_hotkey_registered = False
        self._mouse_listener = None
        self._selection_listener = None
        self._selection_overlay = None
        self._selection_start = None
        self._calibrated_region = None
        self._external_drag_start = None
        self.mirrored_click.connect(self._handle_mirrored_click)
        self.region_selected.connect(self._apply_selected_region)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #17191b; color: #e9edf3; font-family: Segoe UI; font-size: 10pt; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: #17191b; border: 0; }
            QLabel { color: #e3e6eb; }
            QPushButton { background: #292c31; color: #edf0f5; border: 1px solid #383c43; border-radius: 9px; padding: 9px 14px; }
            QPushButton:hover { background: #373c44; border-color: #4b535f; }
            QPushButton:pressed { background: #202329; }
            QLineEdit, QSpinBox, QKeySequenceEdit { background: #25282d; color: #f1f3f6; border: 1px solid #393e46; border-radius: 10px; padding: 8px 10px; selection-background-color: #60aef2; }
            QCheckBox { spacing: 10px; }
            QCheckBox::indicator { width: 19px; height: 19px; border-radius: 5px; border: 2px solid #41464e; background: #202328; }
            QCheckBox::indicator:checked { background: #60aef2; border-color: #60aef2; }
            QSlider::groove:horizontal { height: 6px; background: #343940; border-radius: 3px; }
            QSlider::handle:horizontal { background: #60aef2; width: 16px; margin: -6px 0; border-radius: 8px; }
            QScrollBar:vertical { background: #17191b; width: 10px; margin: 3px; }
            QScrollBar::handle:vertical { background: #41464e; border-radius: 5px; min-height: 35px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        root = QWidget()
        root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root.setStyleSheet("background: transparent;")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(0)

        workspace = QWidget()
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(142)
        self.sidebar.setStyleSheet("QWidget { background: #202328; border-radius: 12px; }")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(7)
        brand = QLabel("CHESS AI")
        brand.setStyleSheet("font-size: 13px; font-weight: 800; color: #60aef2; padding: 5px;")
        sidebar_layout.addWidget(brand)
        self._category_buttons = []
        for category, symbol in (
            ("Alle", "⌂"), ("Engine", "⚙"),
            ("Spielfeld", "▦"), ("Steuerung", "⌨"),
        ):
            button = QPushButton(f"{symbol}   {category}")
            button.setProperty("category", category)
            button.setCheckable(True)
            button.setChecked(category == "Alle")
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 10px 8px; border: 0; background: transparent; }"
                "QPushButton:checked { background: #303943; color: #70baff; border-left: 3px solid #60aef2; }"
            )
            button.clicked.connect(lambda checked=False, name=category: self._select_category(name))
            sidebar_layout.addWidget(button)
            self._category_buttons.append(button)
        sidebar_layout.addStretch(1)
        workspace_layout.addWidget(self.sidebar)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.settings_content = QWidget()
        self.settings_scroll.setWidget(self.settings_content)
        workspace_layout.addWidget(self.settings_scroll, 1)
        root_layout.addWidget(workspace, 1)
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
        self.board_popup = BoardPopup(self.board, None)
        self.board_toggle_button = QPushButton("Spielfeld anzeigen")
        self.board_toggle_button.clicked.connect(self._toggle_board_visibility)
        layout.addWidget(self.board_toggle_button)

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

        self.popup_hotkey_edit, self.popup_hotkey_button, self.popup_hotkey_row_widget = self._make_hotkey_row(
            layout, "Hotkey: Spielfeld ein-/ausblenden", "F7", self._register_popup_hotkey
        )
        self.back_hotkey_edit, self.back_hotkey_button, self.back_hotkey_row_widget = self._make_hotkey_row(
            layout, "Hotkey: Letzten Zug zurücknehmen", "F6", self._register_back_hotkey
        )
        self.opacity_hotkey_edit, self.opacity_hotkey_button, self.opacity_hotkey_row_widget = self._make_hotkey_row(
            layout, "Hotkey: Sichtbarkeit 0 % / 100 %", "F4", self._register_opacity_hotkey
        )

        self.path_edit = QLineEdit(os.environ.get("STOCKFISH_PATH", ""))
        self.path_edit.setPlaceholderText("Pfad zur Stockfish.exe")
        self.browse_button = QPushButton("Durchsuchen …")
        self.browse_button.clicked.connect(self._browse_stockfish)
        self.start_button = QPushButton("Stockfish starten")
        self.start_button.clicked.connect(self._start_engine)
        engine_path_row = QHBoxLayout()
        engine_path_row.addWidget(self.path_edit, 1)
        engine_path_row.addWidget(self.browse_button)
        engine_path_row.addWidget(self.start_button)
        self.engine_path_widget = QWidget()
        self.engine_path_widget.setLayout(engine_path_row)
        layout.addWidget(self.engine_path_widget)

        self.depth = QSpinBox()
        self.depth.setRange(5, 30)
        self.depth.setValue(15)
        self.arrow_count = QSpinBox()
        self.arrow_count.setRange(1, 3)
        self.arrow_count.setValue(3)
        self.arrow_count.setToolTip("Anzahl der angezeigten Engine-Varianten")
        self.arrow_count.valueChanged.connect(self.analysis_multipv_changed.emit)
        engine_options_row = QHBoxLayout()
        engine_options_row.addWidget(QLabel("Pfeile"))
        engine_options_row.addWidget(self.arrow_count)
        engine_options_row.addWidget(QLabel("Analysetiefe"))
        engine_options_row.addWidget(self.depth)
        engine_options_row.addStretch(1)
        self.engine_options_widget = QWidget()
        self.engine_options_widget.setLayout(engine_options_row)
        layout.addWidget(self.engine_options_widget)

        self.region_button = QPushButton("Spielfeldgröße mit Maus markieren")
        self.region_button.clicked.connect(self._start_region_selection)
        layout.addWidget(self.region_button)

        self._setting_widgets = [
            ("Engine", self.engine_path_widget),
            ("Engine", self.engine_options_widget),
            ("Spielfeld", self.board_toggle_button),
            ("Spielfeld", self.mode_controls_widget),
            ("Spielfeld", self.controls_widget),
            ("Spielfeld", self.opacity_row_widget),
            ("Steuerung", self.mode_row_widget),
            ("Steuerung", self.hotkey_row_widget),
            ("Steuerung", self.best_hotkey_row_widget),
            ("Steuerung", self.popup_hotkey_row_widget),
            ("Steuerung", self.back_hotkey_row_widget),
            ("Spielfeld", self.region_button),
        ]
        self._active_category = "Alle"
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Einstellungen suchen …")
        self.search_bar.textChanged.connect(self._filter_settings)
        self.search_button = QPushButton("⌕")
        self.search_button.setFixedWidth(42)
        self.search_button.setToolTip("Suche öffnen")
        self.search_button.clicked.connect(self.search_bar.setFocus)
        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addStretch(1)
        search_layout.addWidget(self.search_button)
        self.search_bar.setMaximumWidth(560)
        search_layout.addWidget(self.search_bar, 4)
        search_layout.addStretch(1)
        layout.insertWidget(0, search_row)
        layout.removeWidget(self.opacity_hotkey_row_widget)
        layout.insertWidget(0, self.opacity_hotkey_row_widget)
        self._search_row = search_row
        self._filter_settings()

        self.board.position_changed.connect(self.engine_position.emit)
        self._load_settings()
        self._connect_setting_persistence()
        self._thread: QThread | None = None
        self._worker: EngineWorker | None = None
        self._register_configured_hotkey()
        self._register_best_move_hotkey()
        self._register_popup_hotkey()
        self._register_extra_hotkeys()
        saved_path = self.path_edit.text().strip()
        if not saved_path or not os.path.isfile(saved_path):
            self.path_edit.clear()
            self._auto_find_stockfish(silent=True)

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

    def _select_category(self, category: str) -> None:
        self._active_category = category
        self.search_bar.clear()
        for button in self._category_buttons:
            button.setChecked(button.property("category") == category)
        self._filter_settings()

    def _filter_settings(self, _query: str = "") -> None:
        query = self.search_bar.text().strip().casefold()
        self._search_row.setVisible(self._active_category == "Alle")
        if query:
            self._active_category = "Alle"
            for button in self._category_buttons:
                button.setChecked(button.property("category") == "Alle")
        for category, widget in self._setting_widgets:
            searchable = category + " " + " ".join(
                child.text() for child in widget.findChildren(QWidget)
                if isinstance(child, (QLabel, QPushButton, QCheckBox, QLineEdit))
            )
            matches_text = not query or query in searchable.casefold()
            matches_category = self._active_category == "Alle" or category == self._active_category
            widget.setVisible(matches_text and matches_category)

    def _load_settings(self) -> None:
        store = self.settings_store
        self.path_edit.setText(store.value("engine/path", self.path_edit.text(), type=str))
        self.depth.setValue(store.value("engine/depth", 15, type=int))
        self.arrow_count.setValue(store.value("engine/arrow_count", 3, type=int))
        self.opacity_slider.setValue(store.value("display/opacity", 100, type=int))
        self.free_move_check.setChecked(store.value("board/free_move", False, type=bool))
        self.pass_through.setChecked(False)
        for key, edit in (
            ("hotkeys/training", self.hotkey_edit),
            ("hotkeys/best_move", self.best_move_hotkey_edit),
            ("hotkeys/popup", self.popup_hotkey_edit),
            ("hotkeys/back", self.back_hotkey_edit),
            ("hotkeys/opacity", self.opacity_hotkey_edit),
        ):
            edit.setKeySequence(QKeySequence(store.value(key, edit.keySequence().toString(), type=str)))

    def _save_settings(self) -> None:
        store = self.settings_store
        values = (
            ("engine/path", self.path_edit.text().strip()),
            ("engine/depth", self.depth.value()),
            ("engine/arrow_count", self.arrow_count.value()),
            ("display/opacity", self.opacity_slider.value()),
            ("board/free_move", self.free_move_check.isChecked()),
            ("hotkeys/training", self.hotkey_edit.keySequence().toString()),
            ("hotkeys/best_move", self.best_move_hotkey_edit.keySequence().toString()),
            ("hotkeys/popup", self.popup_hotkey_edit.keySequence().toString()),
            ("hotkeys/back", self.back_hotkey_edit.keySequence().toString()),
            ("hotkeys/opacity", self.opacity_hotkey_edit.keySequence().toString()),
        )
        for key, value in values:
            store.setValue(key, value)
        store.sync()

    def _connect_setting_persistence(self) -> None:
        self.path_edit.textChanged.connect(self._save_settings)
        self.depth.valueChanged.connect(self._save_settings)
        self.arrow_count.valueChanged.connect(self._save_settings)
        self.opacity_slider.valueChanged.connect(self._save_settings)
        self.free_move_check.toggled.connect(self._save_settings)
        for edit in (self.hotkey_edit, self.best_move_hotkey_edit, self.popup_hotkey_edit,
                     self.back_hotkey_edit, self.opacity_hotkey_edit):
            edit.keySequenceChanged.connect(self._save_settings)

    def _find_stockfish_candidates(self) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        def add(path: str) -> None:
            full = os.path.abspath(os.path.expandvars(path))
            if os.path.isfile(full) and os.path.basename(full).lower() in {"stockfish.exe", "stockfish"}:
                norm = os.path.normcase(full)
                if norm not in seen:
                    seen.add(norm)
                    candidates.append(full)
        for value in (os.environ.get("STOCKFISH_PATH", ""), shutil.which("stockfish"), shutil.which("stockfish.exe")):
            if value:
                add(value)
        roots = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.path.join(os.path.expanduser("~"), "Downloads"),
                 os.path.join(os.path.expanduser("~"), "Documents")]
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for current, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d.lower() not in {"windows", "node_modules", ".git", ".venv", "venv", "__pycache__"}]
                match = next((name for name in files if name.lower() == "stockfish.exe"), None)
                if match:
                    add(os.path.join(current, match))
                    if len(candidates) >= 12:
                        return candidates
        return candidates

    def _auto_find_stockfish(self, silent: bool = False) -> None:
        candidates = self._find_stockfish_candidates()
        if not candidates:
            if not silent:
                self.status.setText("Stockfish nicht automatisch gefunden. Bitte manuell auswählen.")
            return
        if len(candidates) == 1:
            selected = candidates[0]
        else:
            selected, ok = QInputDialog.getItem(self, "Stockfish gefunden", "Gefundene Stockfish-Version:", candidates, 0, False)
            if not ok or not selected:
                return
        self.path_edit.setText(selected)
        self.status.setText("Stockfish gefunden: " + selected)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_board()

    def _fit_board(self, _value: int = 0) -> None:
        if not all(hasattr(self, name) for name in ("board", "board_area")):
            return
        # Feste Standardgröße; die manuelle Brettmarkierung kann sie überschreiben.
        size = 520
        if self._calibrated_region is not None:
            size = min(self._calibrated_region.width(), self._calibrated_region.height())
        size = max(160, size)
        self.board.setMinimumSize(160, 160)
        self.board.setMaximumSize(16777215, 16777215)
        if hasattr(self, "board_popup") and self.board_popup.isVisible() and self._calibrated_region is None:
            self.board_popup.resize(size, size)

    def _start_region_selection(self) -> None:
        if sys.platform != "win32":
            self.status.setText("Bereichsauswahl benötigt Windows.")
            return
        # Ein Overlay pro physischem Monitor vermeiden wir bewusst:
        # ein einzelnes Fenster über virtualGeometry wird von Windows/Qt bei
        # gemischter DPI-Skalierung häufig auf einen Teilbereich begrenzt.
        # Stattdessen wählen wir den Monitor unter dem Mauszeiger.
        screen = QApplication.screenAt(QCursor.pos()) or self.screen() or QApplication.primaryScreen()
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
        # Auswahlrechteck und QWidget-Geometrie verwenden beide Qt-logische
        # globale Koordinaten. Keine DPI-Multiplikation durchführen.
        selected = QRect(x, y, width, height)
        size = min(selected.width(), selected.height())
        if size < 80:
            self.show()
            self.status.setText("Der ausgewählte Bereich ist zu klein.")
            return

        # Das Brett wird exakt in der Mitte des markierten Bereichs platziert.
        left = selected.x() + (selected.width() - size) // 2
        top = selected.y() + (selected.height() - size) // 2
        rect = QRect(left, top, size, size)
        self._calibrated_region = rect

        # Das Popup ist ein eigenständiges Top-Level-Fenster. Geometrie und
        # Auswahl liegen beide in globalen Qt-Koordinaten.
        self.board_popup.hide()
        self.board.setMinimumSize(160, 160)
        self.board.setMaximumSize(16777215, 16777215)
        self.board.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.board_popup.setGeometry(rect)
        self.board_popup.show()
        self.board_popup.raise_()
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

    def _make_hotkey_row(self, layout, label: str, default: str, callback):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QKeySequenceEdit(QKeySequence(default))
        edit.setMaximumWidth(170)
        row.addWidget(edit)
        button = QPushButton("Hotkey übernehmen")
        button.clicked.connect(callback)
        row.addWidget(button)
        widget = QWidget()
        widget.setLayout(row)
        layout.addWidget(widget)
        return edit, button, widget

    def _apply_hotkey(self, edit, hotkey_id: int, attr: str, label: str) -> None:
        if sys.platform != "win32":
            self.status.setText("Globale Hotkeys sind nur unter Windows verfügbar.")
            return
        parts = self._hotkey_parts(edit.keySequence())
        if parts is None:
            self.status.setText(f"Bitte genau eine Tastenkombination für „{label}“ festlegen.")
            return
        if getattr(self, attr):
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), hotkey_id)
            setattr(self, attr, False)
        if ctypes.windll.user32.RegisterHotKey(int(self.winId()), hotkey_id, *parts):
            setattr(self, attr, True)
            self.status.setText(f"Hotkey für „{label}“ gesetzt.")
        else:
            self.status.setText(f"Hotkey für „{label}“ ist bereits belegt oder ungültig.")

    def _register_best_move_hotkey(self) -> None:
        self._apply_hotkey(self.best_move_hotkey_edit, self._best_move_hotkey_id, "_best_move_hotkey_registered", "besten Zug ausführen")

    def _register_popup_hotkey(self) -> None:
        self._apply_hotkey(self.popup_hotkey_edit, self._popup_hotkey_id, "_popup_hotkey_registered", "Spielfeld ein-/ausblenden")

    def _register_back_hotkey(self) -> None:
        self._apply_hotkey(self.back_hotkey_edit, self._back_hotkey_id, "_back_hotkey_registered", "letzten Zug zurücknehmen")

    def _register_opacity_hotkey(self) -> None:
        self._apply_hotkey(self.opacity_hotkey_edit, self._visibility_toggle_hotkey_id, "_visibility_toggle_hotkey_registered", "Sichtbarkeit umschalten")

    def _register_extra_hotkeys(self) -> None:
        self._register_back_hotkey()
        self._register_opacity_hotkey()

    def _toggle_board_opacity(self) -> None:
        self.opacity_slider.setValue(0 if self.opacity_slider.value() > 0 else 100)

    def _execute_best_move(self) -> None:
        if self.board.play_best_move():
            self.status.setText("Bester Zug wurde auf dem Overlay-Brett ausgeführt.")
        else:
            self.status.setText("Kein legaler bester Zug verfügbar. Erst Stockfish starten/Analyse abwarten.")

    def _register_configured_hotkey(self) -> None:
        self._apply_hotkey(self.hotkey_edit, self._hotkey_id, "_hotkey_registered", "Trainingsmodus umschalten")

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
                if msg.message == 0x0312 and msg.wParam == self._back_hotkey_id:
                    self.board.undo()
                    return True, 0
                if msg.message == 0x0312 and msg.wParam == self._visibility_toggle_hotkey_id:
                    self._toggle_board_opacity()
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
        self._worker = EngineWorker(self.path_edit.text().strip(), self.depth.value(), self.arrow_count.value())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self.engine_position.connect(self._worker.set_position)
        self._worker.status.connect(self.status.setText)
        self._worker.failed.connect(self.status.setText)
        self._worker.best_move.connect(self._on_best_move)
        self.analysis_multipv_changed.connect(self._worker.set_multipv)
        self._worker.candidate_moves.connect(self._on_candidate_moves)
        self._thread.start()
        self.start_button.setEnabled(False)

    def _on_candidate_moves(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            self.board.set_candidate_moves([(item["uci"], item["score"]) for item in data[:self.arrow_count.value()]])
        except (ValueError, KeyError, TypeError):
            self.board.set_candidate_moves([])

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
        self._save_settings()
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if sys.platform == "win32":
            for registered, hotkey_id in (
                (self._hotkey_registered, self._hotkey_id),
                (self._best_move_hotkey_registered, self._best_move_hotkey_id),
                (self._popup_hotkey_registered, self._popup_hotkey_id),
                (self._back_hotkey_registered, self._back_hotkey_id),
                (self._visibility_toggle_hotkey_registered, self._visibility_toggle_hotkey_id),
            ):
                if registered:
                    ctypes.windll.user32.UnregisterHotKey(int(self.winId()), hotkey_id)
        if hasattr(self, "board_popup"):
            self.board_popup.close()
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()
