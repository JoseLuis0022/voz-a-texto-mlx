"""Ventana principal: sidebar de navegación + panel central con pestañas/paneles."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.model_manager import MODEL_REPOS, ModelManager
from app.core.scheduler import WorkerPoolScheduler
from app.data.db import Database
from app.paths import resources_dir
from app.ui.dashboard_panel import DashboardPanel
from app.ui.icons import icon
from app.ui.model_panel import ModelPanel
from app.ui.preferences_dialog import PreferencesDialog
from app.ui.queue_panel import QueuePanel
from app.ui.results_panel import ResultsPanel

# (clave de icono, etiqueta)
NAV_ITEMS = [
    ("queue", "Cola"),
    ("dashboard", "Panel"),
    ("models", "Modelos"),
    ("results", "Resultados"),
]

_NAV_ICON_COLOR = "#64748B"      # mismo tono que QListWidget#sidebarList::item
_NAV_ICON_COLOR_ACTIVE = "#1D4ED8"  # mismo tono que ::item:selected


class MainWindow(QMainWindow):
    def __init__(self, db: Database, model_manager: ModelManager, scheduler: WorkerPoolScheduler):
        super().__init__()
        self.db = db
        self.model_manager = model_manager
        self.scheduler = scheduler

        self.setWindowTitle("Voz a Texto")
        self.resize(1180, 760)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebar")
        sidebar_container.setFixedWidth(216)
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        brand_header = QWidget()
        brand_header.setObjectName("brandHeader")
        brand_header.setFixedHeight(64)
        brand_layout = QHBoxLayout(brand_header)
        brand_layout.setContentsMargins(16, 0, 12, 0)
        brand_layout.setSpacing(9)

        logo_label = QLabel()
        icon_path = resources_dir() / "icon.icns"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                logo_label.setPixmap(
                    pixmap.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        brand_layout.addWidget(logo_label)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_title = QLabel('Voz a Texto<span style="color:#2563EB;">.</span>')
        brand_title.setTextFormat(Qt.TextFormat.RichText)
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("Transcripción local")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_subtitle)
        brand_layout.addLayout(brand_text)
        brand_layout.addStretch()

        sidebar_layout.addWidget(brand_header)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebarList")
        self.sidebar.setIconSize(QSize(18, 18))
        for key, label in NAV_ITEMS:
            QListWidgetItem(icon(key, _NAV_ICON_COLOR), label, self.sidebar)
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self.sidebar, stretch=1)

        root_layout.addWidget(sidebar_container)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, stretch=1)

        self.queue_panel = QueuePanel(list(MODEL_REPOS.keys()))
        self.dashboard_panel = DashboardPanel()
        self.model_panel = ModelPanel(model_manager)
        self.results_panel = ResultsPanel()

        default_model = self.db.get_setting("default_model", "large-v3-turbo")
        self.queue_panel.set_current_model(default_model)

        for w in (self.queue_panel, self.dashboard_panel, self.model_panel, self.results_panel):
            self.stack.addWidget(w)

        self.sidebar.setCurrentRow(0)

        self._build_menu()
        self._wire_signals()

        self.scheduler.start()
        self.queue_panel.refresh_all(self.db.list_jobs())
        self.results_panel.refresh(self.db.list_jobs())

    def _build_menu(self) -> None:
        menu = self.menuBar()
        app_menu = menu.addMenu("Voz a Texto")
        prefs_action = app_menu.addAction("Preferencias…")
        prefs_action.triggered.connect(self._open_preferences)

    def _wire_signals(self) -> None:
        self.queue_panel.add_files_requested.connect(self._add_files)
        self.queue_panel.cancel_requested.connect(self.scheduler.cancel_job)
        self.queue_panel.open_result_requested.connect(self._open_result)

        self.scheduler.job_updated.connect(self._on_job_updated)
        self.scheduler.jobs_changed.connect(self._on_jobs_changed)
        self.scheduler.job_failed.connect(self._on_job_failed)
        self.scheduler.stats_tick.connect(self.dashboard_panel.update_stats)

    def _on_nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        for i, (key, _label) in enumerate(NAV_ITEMS):
            color = _NAV_ICON_COLOR_ACTIVE if i == row else _NAV_ICON_COLOR
            self.sidebar.item(i).setIcon(icon(key, color))

    def _add_files(self, paths: list[Path], model_key: str) -> None:
        if not self.model_manager.is_downloaded(model_key):
            QMessageBox.warning(
                self,
                "Modelo no descargado",
                f"El modelo “{model_key}” aún no está descargado. Ve al panel “Modelos” para descargarlo antes de encolar archivos.",
            )
            return
        language = self.db.get_setting("language") or None
        output_dir = Path(self.db.get_setting("output_dir"))
        self.scheduler.enqueue_files(paths, model_key, language, output_dir)

    def _on_job_updated(self, job_id: int) -> None:
        job = self.db.get_job(job_id)
        if job:
            self.queue_panel.update_job(job)
            if job.status == "done":
                self.results_panel.refresh(self.db.list_jobs())

    def _on_jobs_changed(self) -> None:
        self.queue_panel.refresh_all(self.db.list_jobs())
        self.results_panel.refresh(self.db.list_jobs())

    def _on_job_failed(self, job_id: int, message: str) -> None:
        job = self.db.get_job(job_id)
        name = job.display_name if job else str(job_id)
        QMessageBox.critical(self, "Error de transcripción", f"Falló “{name}”:\n\n{message[:500]}")

    def _open_result(self, job_id: int) -> None:
        self.sidebar.setCurrentRow(3)  # Resultados

    def _open_preferences(self) -> None:
        dialog = PreferencesDialog(self.db, self)
        if dialog.exec():
            self.queue_panel.set_current_model(self.db.get_setting("default_model", "large-v3-turbo"))

    def closeEvent(self, event) -> None:
        self.scheduler.shutdown()
        super().closeEvent(event)
