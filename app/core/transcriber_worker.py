"""Proceso hijo persistente: carga un modelo mlx_whisper una vez y transcribe
jobs que le llegan por una cola, reportando progreso por otra cola.

Se lanza con multiprocessing.Process(target=worker_main, args=(model_key, model_dir,
task_queue, progress_queue)). Vive mientras el pool lo necesite; el scheduler lo
apaga enviando None a task_queue.
"""

from __future__ import annotations

import multiprocessing as mp
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Mensajes que este worker manda por progress_queue:
#   ("model_loaded", worker_id, model_key)
#   ("progress", worker_id, job_id, fraction, elapsed_seconds)
#   ("done", worker_id, job_id, result_dict, elapsed_seconds)
#   ("error", worker_id, job_id, error_message)
#   ("idle", worker_id)


@dataclass
class TranscribeTask:
    job_id: int
    source_path: str
    language: Optional[str]  # None => autodetect


def _get_audio_duration(path: str) -> float:
    """Duración en segundos vía el decodificador de audio de mlx_whisper (ffmpeg)."""
    from mlx_whisper.audio import load_audio, SAMPLE_RATE

    audio = load_audio(path)
    return len(audio) / SAMPLE_RATE


def worker_main(
    worker_id: int,
    model_key: str,
    model_dir: str,
    task_queue: "mp.Queue[Optional[TranscribeTask]]",
    progress_queue: "mp.Queue[tuple]",
) -> None:
    import mlx_whisper

    try:
        # "Precarga" real: mlx_whisper.transcribe carga y cachea el modelo internamente
        # la primera vez que se le pasa path_or_hf_repo; para forzar la carga temprana
        # hacemos una transcripción trivial no es viable sin audio, así que en su lugar
        # simplemente señalamos listo y dejamos que la primera tarea pague el load.
        progress_queue.put(("model_loaded", worker_id, model_key))
    except Exception as e:  # pragma: no cover
        progress_queue.put(("error", worker_id, None, f"No se pudo inicializar worker: {e}"))
        return

    while True:
        task = task_queue.get()
        if task is None:
            break  # señal de apagado

        start = time.time()
        try:
            duration = _get_audio_duration(task.source_path)
            progress_queue.put(("duration", worker_id, task.job_id, duration))

            # mlx_whisper.transcribe no soporta callback de progreso nativo: es una
            # sola llamada bloqueante. El progreso mientras corre se estima en el
            # proceso principal (ver scheduler._update_estimated_progress) a partir
            # de la duración del audio y la velocidad histórica del modelo; aquí solo
            # marcamos el arranque y, al final, el resultado con el tiempo real medido.
            progress_queue.put(("progress", worker_id, task.job_id, 0.02, 0.0))

            result = mlx_whisper.transcribe(
                task.source_path,
                path_or_hf_repo=model_dir,
                language=task.language,
                word_timestamps=False,
                verbose=False,
            )

            elapsed = time.time() - start
            progress_queue.put(("done", worker_id, task.job_id, result, elapsed, duration))

        except Exception as e:
            err = f"{e}\n{traceback.format_exc()}"
            progress_queue.put(("error", worker_id, task.job_id, err))

        progress_queue.put(("idle", worker_id))
