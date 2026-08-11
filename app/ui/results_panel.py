"""Panel de resultados: lista de transcripciones completadas con vista previa."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.data.db import Job


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._job_by_item_id: dict[int, Job] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Resultados")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.list_widget)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.meta_label = QLabel("Selecciona un resultado")
        self.meta_label.setObjectName("hintLabel")
        right_layout.addWidget(self.meta_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        right_layout.addWidget(self.preview)

        actions = QHBoxLayout()
        self.reveal_btn = QPushButton("Mostrar en Finder")
        self.reveal_btn.clicked.connect(self._reveal_current)
        actions.addWidget(self.reveal_btn)
        actions.addStretch()
        right_layout.addLayout(actions)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    def refresh(self, jobs: list[Job]) -> None:
        self.list_widget.clear()
        self._job_by_item_id.clear()
        for job in jobs:
            if job.status != "done":
                continue
            item = QListWidgetItem(job.display_name)
            item.setData(Qt.ItemDataRole.UserRole, job.id)
            self.list_widget.addItem(item)
            self._job_by_item_id[job.id] = job

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        job = self._job_by_item_id.get(job_id)
        if not job or not job.result_json_path:
            return
        try:
            data = json.loads(Path(job.result_json_path).read_text(encoding="utf-8"))
        except OSError:
            self.preview.setPlainText("No se pudo leer el resultado.")
            return
        meta = data.get("metadata", {})
        self.meta_label.setText(
            f"Modelo: {meta.get('model')} · Idioma: {meta.get('language_detected')} · "
            f"Duración: {meta.get('duration_seconds', 0):.0f}s · "
            f"Procesado en: {meta.get('processing_seconds', 0):.1f}s · "
            f"Velocidad: {meta.get('speed_realtime_factor', 0):.1f}x tiempo real"
        )
        self.preview.setPlainText(data.get("text", ""))

    def _reveal_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        job_id = item.data(Qt.ItemDataRole.UserRole)
        job = self._job_by_item_id.get(job_id)
        if job and job.result_json_path:
            subprocess.run(["open", "-R", job.result_json_path])
