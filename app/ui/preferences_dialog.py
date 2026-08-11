"""Diálogo de preferencias: límite de paralelismo, carpeta de salida, idioma, modelo por defecto."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from app.core.model_manager import MODEL_REPOS
from app.data.db import Database

LANGUAGES = [
    ("Autodetectar", None),
    ("Español", "es"),
    ("Inglés", "en"),
    ("Portugués", "pt"),
    ("Francés", "fr"),
]


class PreferencesDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Preferencias")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        # Límite de paralelismo
        parallel_row = QHBoxLayout()
        self.parallel_slider = QSlider(Qt.Orientation.Horizontal)
        self.parallel_slider.setMinimum(1)
        self.parallel_slider.setMaximum(6)
        self.parallel_slider.setValue(int(db.get_setting("max_parallel", "3")))
        self.parallel_value_label = QLabel(str(self.parallel_slider.value()))
        self.parallel_slider.valueChanged.connect(lambda v: self.parallel_value_label.setText(str(v)))
        parallel_row.addWidget(self.parallel_slider)
        parallel_row.addWidget(self.parallel_value_label)
        form.addRow("Máx. instancias en paralelo:", parallel_row)

        note = QLabel(
            "La GPU (Metal) se comparte entre instancias: subir mucho este número\n"
            "no garantiza más velocidad, incluso con RAM libre de sobra."
        )
        note.setObjectName("hintLabel")
        form.addRow("", note)

        # Carpeta de salida
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(db.get_setting("output_dir", ""))
        browse_btn = QPushButton("Elegir…")
        browse_btn.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(browse_btn)
        form.addRow("Carpeta de salida:", output_row)

        # Modelo por defecto
        self.model_combo = QComboBox()
        self.model_combo.addItems(list(MODEL_REPOS.keys()))
        current_model = db.get_setting("default_model", "large-v3-turbo")
        if current_model in MODEL_REPOS:
            self.model_combo.setCurrentText(current_model)
        form.addRow("Modelo por defecto:", self.model_combo)

        # Idioma por defecto
        self.language_combo = QComboBox()
        for label, _code in LANGUAGES:
            self.language_combo.addItem(label)
        current_lang = db.get_setting("language", "es")
        for i, (_label, code) in enumerate(LANGUAGES):
            if code == current_lang:
                self.language_combo.setCurrentIndex(i)
                break
        form.addRow("Idioma por defecto:", self.language_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Elige carpeta de salida", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _on_accept(self) -> None:
        self.db.set_setting("max_parallel", self.parallel_slider.value())
        self.db.set_setting("output_dir", self.output_edit.text())
        self.db.set_setting("default_model", self.model_combo.currentText())
        label = self.language_combo.currentText()
        code = next((c for l, c in LANGUAGES if l == label), None)
        self.db.set_setting("language", code or "")
        Path(self.output_edit.text()).mkdir(parents=True, exist_ok=True)
        self.accept()
