"""Panel de dashboard: gráficas en tiempo real de RAM, throughput, e instancias activas."""

from __future__ import annotations

import time

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.effects import apply_card_shadow

pg.setConfigOptions(antialias=True, background=None, foreground="#8a8f99")

_AXIS_PEN = pg.mkPen("#2b2c34", width=1)
_GRID_ALPHA = 0.12


def _style_plot(plot: pg.PlotWidget) -> None:
    """Look consistente para todas las gráficas del dashboard.

    Se fija un color explícito (en vez de transparente): el QGraphicsView
    interno de pyqtgraph cae a la paleta clara por defecto si se le deja
    "None" y no hay stylesheet global forzando el fondo oscuro en QWidget.
    """
    plot.setObjectName("chartCard")
    plot.setBackground("#1b1c22")
    plot.showGrid(x=True, y=True, alpha=_GRID_ALPHA)
    for axis_name in ("left", "bottom"):
        axis = plot.getAxis(axis_name)
        axis.setPen(_AXIS_PEN)
        axis.setTextPen("#8a8f99")
        tick_font = QFont("-apple-system", 10)
        axis.setTickFont(tick_font)
    plot.getPlotItem().titleLabel.item.setDefaultTextColor(pg.mkColor("#c7cad1"))
    plot.setContentsMargins(0, 6, 12, 0)


class _StatTile(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statTile")
        self.setMinimumHeight(78)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("statValue")
        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        layout.addWidget(self.value_label)
        layout.addWidget(title_label)
        apply_card_shadow(self, blur=18, y_offset=4, alpha=70)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class WorkerCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workerCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)
        self.title_label = QLabel("Instancia")
        self.title_label.setObjectName("workerCardTitle")
        self.file_label = QLabel("—")
        self.detail_label = QLabel("—")
        self.detail_label.setObjectName("hintLabel")
        layout.addWidget(self.title_label)
        layout.addWidget(self.file_label)
        layout.addWidget(self.detail_label)
        apply_card_shadow(self, blur=18, y_offset=4, alpha=70)

    def update_data(self, worker: dict) -> None:
        self.title_label.setText(f"Instancia #{worker['worker_id']} · {worker['model']}")
        self.file_label.setText(worker.get("file_name") or "Inactiva")
        speed = worker.get("speed")
        speed_text = f"{speed:.1f}x tiempo real" if speed else "—"
        pct = int((worker.get("progress") or 0) * 100)
        self.detail_label.setText(f"{pct}% · {speed_text} · {worker['ram_mb']:.0f} MB RAM")


class DashboardPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_time = time.time()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(16)

        kicker = QLabel("EN VIVO")
        kicker.setObjectName("panelKicker")
        root.addWidget(kicker)

        title = QLabel("Panel de rendimiento")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        # --- fila de tarjetas resumen ---
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(12)
        self.tile_ram = _StatTile("RAM en uso")
        self.tile_workers = _StatTile("Instancias activas")
        self.tile_queue = _StatTile("En cola")
        self.tile_done = _StatTile("Completados")
        for t in (self.tile_ram, self.tile_workers, self.tile_queue, self.tile_done):
            tiles_row.addWidget(t)
        root.addLayout(tiles_row)

        # --- gráfica de RAM ---
        self.ram_plot = pg.PlotWidget(title="RAM del sistema (MB)")
        _style_plot(self.ram_plot)
        self.ram_plot.addLegend(offset=(10, 10), brush=pg.mkBrush("#1b1c22"), pen=pg.mkPen("#2b2c34"), labelTextColor="#c7cad1")
        self.ram_used_curve = self.ram_plot.plot(pen=pg.mkPen("#3b82f6", width=2), name="Usada")
        self.ram_avail_curve = self.ram_plot.plot(pen=pg.mkPen("#34d399", width=2), name="Disponible")
        root.addWidget(self.ram_plot, stretch=2)

        # --- gráfica de throughput ---
        self.throughput_plot = pg.PlotWidget(title="Throughput acumulado (segundos de audio transcritos)")
        _style_plot(self.throughput_plot)
        self.throughput_curve = self.throughput_plot.plot(pen=pg.mkPen("#f0b459", width=2))
        root.addWidget(self.throughput_plot, stretch=2)

        # --- tarjetas de instancias activas ---
        instances_title = QLabel("Instancias en ejecución")
        instances_title.setObjectName("sectionTitle")
        root.addWidget(instances_title)

        self.workers_container = QWidget()
        self.workers_layout = QGridLayout(self.workers_container)
        self.workers_layout.setSpacing(12)
        root.addWidget(self.workers_container, stretch=1)

        self._worker_cards: dict[int, WorkerCard] = {}

    def update_stats(self, stats: dict) -> None:
        self.tile_ram.set_value(f"{stats['ram_used_mb']:.0f} MB")
        active = sum(1 for w in stats["workers"] if w["busy"])
        self.tile_workers.set_value(str(active))
        self.tile_queue.set_value(str(stats["counts"].get("pending", 0)))
        self.tile_done.set_value(str(stats["counts"].get("done", 0)))

        history = stats["ram_history"]
        if history:
            xs = [t - history[0][0] for t, _ in history]
            used_ys = [v for _, v in history]
            self.ram_used_curve.setData(xs, used_ys)
            total = stats["ram_total_mb"]
            avail_ys = [total - v for v in used_ys]
            self.ram_avail_curve.setData(xs, avail_ys)

        tput = stats["throughput_history"]
        if tput:
            xs = [t - tput[0][0] for t, _ in tput]
            ys = [v for _, v in tput]
            self.throughput_curve.setData(xs, ys)

        self._update_worker_cards(stats["workers"])

    def _update_worker_cards(self, workers: list[dict]) -> None:
        seen_ids = set()
        for i, w in enumerate(workers):
            seen_ids.add(w["worker_id"])
            card = self._worker_cards.get(w["worker_id"])
            if card is None:
                card = WorkerCard()
                self._worker_cards[w["worker_id"]] = card
                self.workers_layout.addWidget(card, i // 3, i % 3)
            card.update_data(w)

        for wid in list(self._worker_cards.keys()):
            if wid not in seen_ids:
                card = self._worker_cards.pop(wid)
                self.workers_layout.removeWidget(card)
                card.deleteLater()

        if not workers:
            pass  # se podría mostrar un placeholder "sin instancias activas"
