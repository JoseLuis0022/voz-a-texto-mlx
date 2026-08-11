"""Punto de entrada de la app Voz a Texto."""

from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from app.core.model_manager import ModelManager
from app.core.scheduler import WorkerPoolScheduler
from app.data.db import Database
from app.ui.main_window import MainWindow

RESOURCES_DIR = Path(__file__).parent / "resources"

# Tipografía de marca (ver Guía de Diseño): DM Sans. Se embebe como .woff2 por
# peso (Qt 6 puede cargar woff2 vía FreeType) en vez de depender de que el
# usuario la tenga instalada o de una CDN.
FONT_FILES = [
    "DMSans-Light.woff2",
    "DMSans-Regular.woff2",
    "DMSans-Medium.woff2",
    "DMSans-SemiBold.woff2",
    "DMSans-Bold.woff2",
    "DMSans-ExtraBold.woff2",
]


def _load_brand_font() -> str:
    """Carga los pesos de DM Sans embebidos y devuelve el nombre de familia
    real que Qt les asignó (puede diferir del nombre "DM Sans" nominal, p. ej.
    "DM Sans 9pt" al provenir de una instancia con eje óptico). Si algo falla,
    devuelve "DM Sans" tal cual — el QSS ya trae fallbacks al stack del sistema."""
    resolved_family = "DM Sans"
    fonts_dir = RESOURCES_DIR / "fonts"
    for filename in FONT_FILES:
        path = fonts_dir / filename
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            resolved_family = families[0]
    return resolved_family


def main() -> int:
    # Necesario en macOS con PyInstaller / apps empaquetadas: evita relanzar la app
    # completa en cada proceso hijo (spawn es el método por defecto en macOS).
    mp.freeze_support()

    app = QApplication(sys.argv)
    app.setApplicationName("Voz a Texto")

    icon_path = RESOURCES_DIR / "icon.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    brand_font_family = _load_brand_font()

    qss_path = RESOURCES_DIR / "style.qss"
    if qss_path.exists():
        qss = qss_path.read_text(encoding="utf-8")
        qss = qss.replace('"DM Sans"', f'"{brand_font_family}"')
        app.setStyleSheet(qss)

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
