from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from chess_ai_v2.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Chess AI V2")
    app.setOrganizationName("Robin")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
