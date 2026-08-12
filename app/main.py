"""Punto de entrada de la app Voz a Texto."""

from __future__ import annotations

import multiprocessing as mp
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.model_manager import ModelManager
from app.core.scheduler import WorkerPoolScheduler
from app.data.db import Database
from app.paths import resources_dir
from app.ui.main_window import MainWindow


RESOURCES_DIR = resources_dir()

# Nombre único para el canal local usado como candado de instancia única.
_SINGLE_INSTANCE_KEY = "VozATexto-instancia-unica"


def _acquire_single_instance_lock() -> QLocalServer | None:
    """Garantiza que solo haya una instancia de la app corriendo a la vez.

    Intenta conectarse como cliente a un servidor local existente: si lo
    logra, ya hay una instancia abierta y devolvemos None. Si no, esta
    instancia se convierte en el servidor y devuelve el QLocalServer (hay
    que mantener la referencia viva mientras la app corre).
    """
    socket = QLocalSocket()
    socket.connectToServer(_SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(200):
        socket.disconnectFromServer()
        return None

    # No había servidor: puede que quedara un socket huérfano de un cierre
    # anterior en falso (crash). Lo removemos antes de escuchar.
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)

    server = QLocalServer()
    server.listen(_SINGLE_INSTANCE_KEY)
    return server

# Tipografía de marca: Inter (la misma que usa el frontend de Farmora, la
# referencia de diseño). Se embebe como .woff2 por peso (Qt 6 puede cargar
# woff2 vía FreeType) en vez de depender de que el usuario la tenga instalada.
FONT_FILES = [
    "Inter-Regular.woff2",
    "Inter-Medium.woff2",
    "Inter-SemiBold.woff2",
    "Inter-Bold.woff2",
]


def _load_brand_font() -> str:
    """Carga los pesos de Inter embebidos y devuelve el nombre de familia real
    que Qt les asignó. Si algo falla, devuelve "Inter" tal cual — el QSS ya
    trae fallbacks al stack del sistema."""
    resolved_family = "Inter"
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

    lock_server = _acquire_single_instance_lock()
    if lock_server is None:
        QMessageBox.information(
            None,
            "Voz a Texto",
            "Voz a Texto ya está abierto.",
        )
        return 0

    icon_path = RESOURCES_DIR / "icon.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    brand_font_family = _load_brand_font()

    qss_path = RESOURCES_DIR / "style.qss"
    if qss_path.exists():
        qss = qss_path.read_text(encoding="utf-8")
        qss = qss.replace('"Inter"', f'"{brand_font_family}"')
        app.setStyleSheet(qss)

    db = Database()
    Path(db.get_setting("output_dir")).mkdir(parents=True, exist_ok=True)

    model_manager = ModelManager()
    scheduler = WorkerPoolScheduler(db, model_manager)

    # BUG que causaba procesos worker huérfanos (cada uno con un modelo Whisper
    # cargado en RAM) acumulándose en segundo plano en cada cierre de la app:
    # nunca se llamaba a scheduler.shutdown(). aboutToQuit es la señal de Qt
    # que sí dispara siempre que la app termina de forma normal (Cmd+Q, cerrar
    # la ventana, menú Salir), así que es el único punto de salida que
    # necesitamos cubrir para el caso normal.
    app.aboutToQuit.connect(scheduler.shutdown)

    # Caso "cierre sucio" (kill/pkill/Activity Monitor -> Salir forzado, que
    # manda SIGTERM): sin este handler, Python simplemente muere sin correr
    # aboutToQuit y los workers quedan huérfanos igual. Se traduce la señal a
    # un app.quit() normal para que pase por el mismo camino de limpieza.
    def _handle_termination(signum, frame) -> None:  # noqa: ANN001
        app.quit()

    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, _handle_termination)

    # Python solo entrega señales entre instrucciones del intérprete; el loop
    # de eventos de Qt es un bucle C++ que no le cede el control salvo que
    # haya algo Python-side despertando periódicamente. Este timer no-op es
    # el truco estándar para que SIGTERM/SIGINT no se queden "atorados".
    signal_pump = QTimer()
    signal_pump.timeout.connect(lambda: None)
    signal_pump.start(200)

    window = MainWindow(db, model_manager, scheduler)
    window.show()

    exit_code = app.exec()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
