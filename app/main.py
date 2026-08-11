"""Punto de entrada de la app Voz a Texto."""

from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.core.model_manager import ModelManager
from app.core.scheduler import WorkerPoolScheduler
from app.data.db import Database
from app.ui.main_window import MainWindow

RESOURCES_DIR = Path(__file__).parent / "resources"


def main() -> int:
    # Necesario en macOS con PyInstaller / apps empaquetadas: evita relanzar la app
    # completa en cada proceso hijo (spawn es el método por defecto en macOS).
    mp.freeze_support()

    app = QApplication(sys.argv)
    app.setApplicationName("Voz a Texto")

    qss_path = RESOURCES_DIR / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    db = Database()
    Path(db.get_setting("output_dir")).mkdir(parents=True, exist_ok=True)

    model_manager = ModelManager()
    scheduler = WorkerPoolScheduler(db, model_manager)

    window = MainWindow(db, model_manager, scheduler)
    window.show()

    exit_code = app.exec()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
