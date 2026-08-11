"""Panel de gestión de modelos: descarga de large-v3 / large-v3-turbo con progreso."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.model_manager import ModelInfo, ModelManager


class _DownloadThread(QThread):
    progress = Signal(str, float, str)
    finished_ok = Signal(str)
    failed = Signal(str, str)

    def __init__(self, manager: ModelManager, model_key: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.model_key = model_key

    def run(self) -> None:
        try:
            self.manager.download(self.model_key, on_progress=self.progress.emit)
            self.finished_ok.emit(self.model_key)
        except Exception as e:
            self.failed.emit(self.model_key, str(e))


class _ModelRow(QFrame):
    download_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, info: ModelInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("modelRow")
        self.model_key = info.key

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(info.key)
        name.setObjectName("modelName")
        top.addWidget(name)
        top.addStretch()

        self.size_label = QLabel(f"~{info.approx_size_mb} MB")
        self.size_label.setObjectName("hintLabel")
        top.addWidget(self.size_label)

        self.action_btn = QPushButton()
        top.addWidget(self.action_btn)
        layout.addLayout(top)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setObjectName("hintLabel")
        layout.addWidget(self.status_label)

        self.set_downloaded(info.downloaded)
        self.action_btn.clicked.connect(self._on_click)

    def set_downloaded(self, downloaded: bool) -> None:
        self._downloaded = downloaded
        self.action_btn.setText("Eliminar" if downloaded else "Descargar")
        self.status_label.setText("Descargado, listo para usar" if downloaded else "No descargado")
        self.progress_bar.setVisible(False)

    def _on_click(self) -> None:
        if self._downloaded:
            self.delete_requested.emit(self.model_key)
        else:
            self.download_requested.emit(self.model_key)

    def set_downloading(self) -> None:
        self.action_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Iniciando descarga…")

    def update_progress(self, fraction: float, text: str) -> None:
        self.progress_bar.setValue(int(fraction * 100))
        self.status_label.setText(text)

    def set_finished(self) -> None:
        self.action_btn.setEnabled(True)
        self.set_downloaded(True)

    def set_failed(self, message: str) -> None:
        self.action_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {message}")


class ModelPanel(QWidget):
    model_downloaded = Signal(str)

    def __init__(self, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.model_manager = model_manager
        self._threads: dict[str, _DownloadThread] = {}
        self._rows: dict[str, _ModelRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Modelos")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        hint = QLabel("Descarga los modelos Whisper (formato MLX) que quieras usar para transcribir.")
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

        for info in self.model_manager.list_models():
            row = _ModelRow(info)
            row.download_requested.connect(self._start_download)
            row.delete_requested.connect(self._delete_model)
            self._rows[info.key] = row
            layout.addWidget(row)

        layout.addStretch()

    def _start_download(self, model_key: str) -> None:
        row = self._rows[model_key]
        row.set_downloading()
        thread = _DownloadThread(self.model_manager, model_key)
        thread.progress.connect(lambda key, frac, text: self._rows[key].update_progress(frac, text))
        thread.finished_ok.connect(self._on_finished)
        thread.failed.connect(lambda key, msg: self._rows[key].set_failed(msg))
        self._threads[model_key] = thread
        thread.start()

    def _on_finished(self, model_key: str) -> None:
        self._rows[model_key].set_finished()
        self.model_downloaded.emit(model_key)

    def _delete_model(self, model_key: str) -> None:
        self.model_manager.delete(model_key)
        self._rows[model_key].set_downloaded(False)
