from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

PROCESS_STARTED_AT = time.perf_counter()

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .paths import app_data_dir
from .single_instance import SingleInstanceGuard
from .startup_metrics import StartupTimeline

if TYPE_CHECKING:
    from .main_window import MainWindow


def _activate_window(win: "MainWindow") -> None:
    if win.isMinimized():
        win.showNormal()
    else:
        win.show()
    win.raise_()
    win.activateWindow()


def main() -> int:
    startup = StartupTimeline(started_at=PROCESS_STARTED_AT)
    startup.mark("app_module_ready")

    app = QApplication(sys.argv)
    app.setApplicationName("Chiasm")
    app.setOrganizationName("Chiasm")
    startup.mark("qapplication_ready")

    guard = SingleInstanceGuard(app_data_dir())
    if not guard.acquire():
        # A live Chiasm GUI already owns the lock. Avoid importing the heavy
        # desktop window graph at all in this short-lived secondary process.
        startup.mark("secondary_instance_forwarded")
        trace_path = str(os.environ.get("MELODEX_STARTUP_TRACE") or "").strip()
        if trace_path:
            startup.write_json(trace_path)
        return 0
    startup.mark("single_instance_ready")

    icon_path = Path(__file__).resolve().parent / "assets" / "chiasm-mark.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    startup.mark("app_identity_ready")

    # Delay the largest import graph until after the single-instance decision
    # and record it separately from MainWindow construction.
    startup.mark("main_window_import_start")
    from .main_window import MainWindow
    startup.mark("main_window_import_ready")

    startup.mark("main_window_construct_start")
    win = MainWindow(startup_timeline=startup)
    win.enter_chiasm_mode()
    startup.mark("main_window_construct_ready")

    guard.activationRequested.connect(lambda: _activate_window(win))
    app.aboutToQuit.connect(guard.release)
    win.show()
    startup.mark("window_show_requested")

    trace_path = str(os.environ.get("MELODEX_STARTUP_TRACE") or "").strip()
    probe_exit = str(os.environ.get("MELODEX_STARTUP_PROBE_EXIT") or "").strip()

    def first_event_loop_turn() -> None:
        startup.mark("first_event_loop_turn")
        if trace_path:
            startup.write_json(trace_path)
        if probe_exit:
            # Let deferred show/paint callbacks run before quitting the
            # headless startup probe.
            QTimer.singleShot(0, win.close)

    QTimer.singleShot(0, first_event_loop_turn)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
