"""Descarga y gestión de los modelos Whisper (formato MLX) desde Hugging Face."""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError

from app.data.db import MODELS_DIR

# Repos oficiales de mlx-community (conversión MLX de los pesos de Whisper de OpenAI)
MODEL_REPOS = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

# Tamaños aproximados en disco, solo para mostrar una estimación antes de descargar
MODEL_APPROX_SIZE_MB = {
    "large-v3": 3100,
    "large-v3-turbo": 1650,
}

ProgressCallback = Callable[[str, float, str], None]  # (model_key, fraction 0..1, status_text)


@dataclass
class ModelInfo:
    key: str
    repo_id: str
    local_path: Path
    downloaded: bool
    approx_size_mb: int


class ModelManager:
    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def local_dir_for(self, model_key: str) -> Path:
        return self.models_dir / model_key

    def is_downloaded(self, model_key: str) -> bool:
        d = self.local_dir_for(model_key)
        if not d.exists() or not (d / "config.json").exists():
            return False
        # Los repos de mlx-community no siempre usan el mismo formato de pesos
        # (algunos publican weights.npz, otros weights.safetensors o *.safetensors).
        has_weights = any(d.glob("*.safetensors")) or (d / "weights.npz").exists()
        return has_weights

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                key=key,
                repo_id=repo,
                local_path=self.local_dir_for(key),
                downloaded=self.is_downloaded(key),
                approx_size_mb=MODEL_APPROX_SIZE_MB.get(key, 0),
            )
            for key, repo in MODEL_REPOS.items()
        ]

    def download(self, model_key: str, on_progress: Optional[ProgressCallback] = None) -> Path:
        """Descarga el modelo a models_dir/<model_key>. Bloqueante: llamar desde un hilo/proceso.

        huggingface_hub no expone un callback de progreso agregado simple, así que
        mientras la descarga corre en este hilo lanzamos un hilo "poller" que estima
        el % comparando el tamaño en disco acumulado contra el tamaño aproximado del
        modelo, y lo reporta a `on_progress` cada ~0.5s.
        """
        if model_key not in MODEL_REPOS:
            raise ValueError(f"Modelo desconocido: {model_key}")

        repo_id = MODEL_REPOS[model_key]
        target = self.local_dir_for(model_key)
        target.mkdir(parents=True, exist_ok=True)
        approx_mb = max(MODEL_APPROX_SIZE_MB.get(model_key, 1), 1)

        stop_event = threading.Event()

        def poll() -> None:
            while not stop_event.is_set():
                mb = self.disk_usage_mb(model_key)
                fraction = min(mb / approx_mb, 0.99)
                if on_progress:
                    on_progress(model_key, fraction, f"{mb:.0f} MB / ~{approx_mb} MB")
                stop_event.wait(0.5)

        poller = threading.Thread(target=poll, daemon=True)
        if on_progress:
            on_progress(model_key, 0.0, "Iniciando descarga…")
            poller.start()

        try:
            snapshot_download(repo_id=repo_id, local_dir=str(target))
        except HfHubHTTPError as e:
            raise RuntimeError(f"Error descargando {model_key}: {e}") from e
        finally:
            stop_event.set()
            if poller.is_alive():
                poller.join(timeout=1.0)

        if on_progress:
            on_progress(model_key, 1.0, "Completado")

        return target

    def delete(self, model_key: str) -> None:
        d = self.local_dir_for(model_key)
        if d.exists():
            shutil.rmtree(d)

    def disk_usage_mb(self, model_key: str) -> float:
        d = self.local_dir_for(model_key)
        if not d.exists():
            return 0.0
        total = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        return total / (1024 * 1024)
