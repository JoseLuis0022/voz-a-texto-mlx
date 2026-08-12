"""Utilidades visuales compartidas (Qt Style Sheets no soporta box-shadow)."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def apply_card_shadow(widget: QWidget, blur: int = 16, y_offset: int = 3, alpha: int = 35) -> None:
    """Aplica una sombra suave tipo 'card elevada' a un QFrame/QWidget.

    Valores por defecto calibrados para tema claro (equivalente a un
    `shadow-md` de Tailwind: sutil, no la sombra oscura de un tema dark)."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)
