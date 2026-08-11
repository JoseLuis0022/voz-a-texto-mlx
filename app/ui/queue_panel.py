"""Panel de cola: tabla de trabajos con drag&drop, progreso, estado y acciones."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import Job

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".flac", ".ogg", ".webm", ".aac"}

STATUS_LABELS = {
    "pending": "En cola",
    "running": "Procesando",
    "done": "Completado",
    "error": "Error",
    "canceled": "Cancelado",
}

COLUMNS = ["Archivo", "Modelo", "Estado", "Progreso", "Velocidad", "Duración", ""]


class _EmptyState(QWidget):
    """Placeholder mostrado cuando la cola está vacía."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        icon = QLabel("🎙️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")
        layout.addWidget(icon)

        title = QLabel("Sin archivos en cola")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        subtitle = QLabel("Arrastra audio o vídeo aquí para empezar a transcribir")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("hintLabel")
        layout.addWidget(subtitle)


class QueuePanel(QWidget):
    files_dropped = Signal(list)      # list[Path]
    add_files_requested = Signal(list, str)  # list[Path], model_key
    cancel_requested = Signal(int)    # job_id
    open_result_requested = Signal(int)  # job_id

    def __init__(self, available_models: list[str], parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._job_row: dict[int, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        kicker = QLabel("TRANSCRIPCIÓN")
        kicker.setObjectName("panelKicker")
        layout.addWidget(kicker)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("Cola de trabajo")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        model_label = QLabel("Modelo:")
        model_label.setObjectName("hintLabel")
        header.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(available_models)
        self.model_combo.setMinimumWidth(150)
        header.addWidget(self.model_combo)

        add_btn = QPushButton("＋ Añadir archivos…")
        add_btn.setProperty("variant", "primary")
        add_btn.clicked.connect(self._pick_files)
        header.addWidget(add_btn)
        layout.addLayout(header)

        hint = QLabel(
            "Arrastra archivos de audio/vídeo aquí, o usa “Añadir archivos…”. "
            "El modelo elegido arriba se usará para todo lo que encoles a continuación."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(COLUMNS)):
            header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        # ResizeToContents no mide bien los QWidget insertados con setCellWidget
        # (progreso, botones de acción) — se fijan anchos explícitos generosos.
        self.table.setColumnWidth(1, 130)  # Modelo
        self.table.setColumnWidth(2, 110)  # Estado
        self.table.setColumnWidth(3, 130)  # Progreso
        self.table.setColumnWidth(4, 90)   # Velocidad
        self.table.setColumnWidth(5, 90)   # Duración
        self.table.setColumnWidth(6, 100)  # Acciones

        self._empty_state = _EmptyState()

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._empty_state)  # índice 0
        self.content_stack.addWidget(self.table)          # índice 1
        layout.addWidget(self.content_stack, stretch=1)

    # ---- drag & drop ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                paths.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXTENSIONS))
            elif p.suffix.lower() in AUDIO_EXTENSIONS:
                paths.append(p)
        if paths:
            self.add_files_requested.emit(paths, self.model_combo.currentText())

    def _pick_files(self) -> None:
        exts = " ".join(f"*{e}" for e in AUDIO_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, "Selecciona archivos de audio/vídeo", "", f"Audio/Vídeo ({exts})")
        if files:
            self.add_files_requested.emit([Path(f) for f in files], self.model_combo.currentText())

    def set_current_model(self, model_key: str) -> None:
        idx = self.model_combo.findText(model_key)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    # ---- refresco de datos ----
    def refresh_all(self, jobs: list[Job]) -> None:
        self.table.setRowCount(0)
        self._job_row.clear()
        for job in jobs:
            self._insert_row(job)
        self._sync_empty_state()

    def update_job(self, job: Job) -> None:
        row = self._job_row.get(job.id)
        if row is None:
            self._insert_row(job)
            self._sync_empty_state()
            return
        self._fill_row(row, job)

    def _sync_empty_state(self) -> None:
        self.content_stack.setCurrentIndex(1 if self.table.rowCount() else 0)

    def _insert_row(self, job: Job) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._job_row[job.id] = row
        self._fill_row(row, job)

    def _fill_row(self, row: int, job: Job) -> None:
        self.table.setItem(row, 0, QTableWidgetItem(job.display_name))
        self.table.setItem(row, 1, QTableWidgetItem(job.model))
        self.table.setItem(row, 2, QTableWidgetItem(STATUS_LABELS.get(job.status, job.status)))

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(job.progress * 100))
        bar.setTextVisible(True)
        self.table.setCellWidget(row, 3, bar)

        speed_text = f"{job.speed_realtime:.1f}x" if job.speed_realtime else "—"
        self.table.setItem(row, 4, QTableWidgetItem(speed_text))

        dur_text = f"{job.duration_seconds:.0f}s" if job.duration_seconds else "—"
        self.table.setItem(row, 5, QTableWidgetItem(dur_text))

        actions = QWidget()
        h = QHBoxLayout(actions)
        h.setContentsMargins(4, 2, 4, 2)
        if job.status == "pending":
            btn = QPushButton("Quitar")
            btn.setProperty("variant", "tableAction")
            btn.clicked.connect(lambda: self.cancel_requested.emit(job.id))
            h.addWidget(btn)
        elif job.status == "done":
            btn = QPushButton("Abrir")
            btn.setProperty("variant", "tableAction")
            btn.clicked.connect(lambda: self.open_result_requested.emit(job.id))
            h.addWidget(btn)
        elif job.status == "error":
            full_message = job.error_message or "Error"
            short_message = full_message if len(full_message) <= 16 else full_message[:14] + "…"
            lbl = QLabel(short_message)
            lbl.setObjectName("errorLabel")
            lbl.setToolTip(full_message)
            h.addWidget(lbl)
        self.table.setCellWidget(row, 6, actions)
