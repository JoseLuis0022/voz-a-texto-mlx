"""Iconos vectoriales estilo outline (línea fina, stroke-width 2), en el
mismo espíritu que los íconos de Farmora (familia lucide/heroicons).

Se generan a partir de paths SVG embebidos —sin depender de assets
externos ni de una fuente de iconos instalada— y se rasterizan al color
pedido, así se pueden recolorear en caliente según el estado (p. ej. item
de sidebar normal vs. seleccionado) sin mantener un archivo por color.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Paths adaptados del set outline de Lucide (ISC license), viewBox 24x24,
# stroke-width 2, sin relleno — mismo lenguaje visual que los iconos usados
# en el frontend de Farmora.
_ICONS: dict[str, str] = {
    # Cola: lista de líneas (inbox/list)
    "queue": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    # Panel: mini gráfico de barras
    "dashboard": '<path d="M3 3v18h18"/><path d="M8 17v-5"/><path d="M13 17V7"/><path d="M18 17v-9"/>',
    # Modelos: caja/paquete
    "models": '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
    # Resultados: documento con líneas de texto
    "results": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
    # Micrófono, usado como placeholder en el estado vacío de la cola
    "mic": (
        '<path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
        '<path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4M9 22h6"/>'
    ),
}


def _svg_document(name: str, color: str) -> str:
    body = _ICONS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def icon_pixmap(name: str, color: str = "#64748B", size: int = 18) -> QPixmap:
    """Rasteriza un icono a un QPixmap cuadrado transparente del color pedido."""
    renderer = QSvgRenderer(QByteArray(_svg_document(name, color).encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def icon(name: str, color: str = "#64748B", size: int = 18) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))
