"""Resolución de rutas a app/resources, válida tanto corriendo desde código
fuente como empaquetado con PyInstaller.

En un .app de PyInstaller, los módulos .py de la propia app no existen como
archivos sueltos en disco: viven comprimidos dentro del PYZ, así que
Path(__file__) ya no apunta a una ruta real y cualquier `.exists()` sobre
ella da False. PyInstaller expone la carpeta real donde sí quedaron los
archivos declarados en `datas` (packaging/VozATexto.spec) vía sys._MEIPASS.
Módulo centralizado para no repetir este condicional en cada sitio que
necesita cargar un recurso (icono, .qss, fuentes...).
"""

from __future__ import annotations

import sys
from pathlib import Path


def resources_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "resources"
