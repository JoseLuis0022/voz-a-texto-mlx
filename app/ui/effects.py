"""Utilidades visuales compartidas (Qt Style Sheets no soporta box-shadow)."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def apply_card_shadow(widget: QWidget, blur: int = 22, y_offset: int = 6, alpha: int = 90) -> None:
    """Aplica una sombra suave tipo 'card elevada' a un QFrame/QWidget."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)
