"""Proceso hijo persistente: carga un modelo mlx_whisper una vez y transcribe
jobs que le llegan por una cola, reportando progreso por otra cola.

Se lanza con multiprocessing.Process(target=worker_main, args=(model_key, model_dir,
task_queue, progress_queue)). Vive mientras el pool lo necesite; el scheduler lo
apaga enviando None a task_queue.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.media_types import VIDEO_EXTENSIONS

# Cuando la app corre como .app empaquetado y se abre con doble clic desde
# Finder (o LaunchServices en general), el proceso hereda un PATH mínimo que
# no incluye Homebrew — así que "ffmpeg" no se encuentra aunque esté
# instalado. Se completa el PATH con las rutas típicas de Homebrew (Apple
# Silicon e Intel) antes de que este proceso hijo invoque ffmpeg, sea
# directamente (_extract_audio) o indirectamente (mlx_whisper.audio.load_audio).
for _extra_bin_dir in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _extra_bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _extra_bin_dir + os.pathsep + os.environ.get("PATH", "")

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


def _extract_audio(source_path: str) -> str:
    """Extrae solo la pista de audio de un archivo de vídeo a un .wav temporal
    de 16kHz mono (el formato que espera Whisper).

    Se hace una sola vez por job y ese .wav se reutiliza tanto para medir la
    duración como para transcribir, en vez de dejar que Whisper desmuxe el
    contenedor de vídeo dos veces por su cuenta. El vídeo en sí nunca se
    decodifica: ffmpeg descarta la pista de vídeo (-vn) sin tocarla.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="voz_a_texto_audio_")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", source_path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        tmp_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as e:
        os.unlink(tmp_path)
        raise RuntimeError(
            "ffmpeg no está instalado o no está en el PATH; hace falta para procesar vídeos."
        ) from e
    except subprocess.CalledProcessError as e:
        os.unlink(tmp_path)
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        raise RuntimeError(f"No se pudo extraer el audio del vídeo: {stderr[-500:]}") from e
    return tmp_path


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
        extracted_audio_path: Optional[str] = None
        try:
            is_video = Path(task.source_path).suffix.lower() in VIDEO_EXTENSIONS
            audio_path = task.source_path
            if is_video:
                extracted_audio_path = _extract_audio(task.source_path)
                audio_path = extracted_audio_path

            duration = _get_audio_duration(audio_path)
            progress_queue.put(("duration", worker_id, task.job_id, duration))

            # mlx_whisper.transcribe no soporta callback de progreso nativo: es una
            # sola llamada bloqueante. El progreso mientras corre se estima en el
            # proceso principal (ver scheduler._update_estimated_progress) a partir
            # de la duración del audio y la velocidad histórica del modelo; aquí solo
            # marcamos el arranque y, al final, el resultado con el tiempo real medido.
            progress_queue.put(("progress", worker_id, task.job_id, 0.02, 0.0))

            result = mlx_whisper.transcribe(
                audio_path,
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

        finally:
            if extracted_audio_path:
                Path(extracted_audio_path).unlink(missing_ok=True)

        progress_queue.put(("idle", worker_id))
