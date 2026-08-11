"""WorkerPoolScheduler: gestiona un pool de procesos worker persistentes,
decide cuándo lanzar nuevos según RAM libre y el límite configurado, y traduce
los mensajes de los procesos hijos a señales Qt para la UI.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from app.core.model_manager import ModelManager
from app.core.outputs import write_outputs
from app.core.transcriber_worker import TranscribeTask, worker_main
from app.data.db import Database, Job

# Factor de velocidad esperado por modelo, usado solo para ESTIMAR el progreso
# visual mientras el proceso hijo transcribe (llamada bloqueante sin callback interno).
# Se recalibra en caliente con la velocidad real observada de trabajos anteriores.
DEFAULT_SPEED_GUESS = {
    "large-v3": 1.8,
    "large-v3-turbo": 5.5,
}


@dataclass
class _ActiveWorker:
    worker_id: int
    process: mp.Process
    task_queue: mp.Queue
    model_key: str
    current_job_id: Optional[int] = None
    busy: bool = False
    started_job_at: Optional[float] = None
    job_duration: Optional[float] = None
    ram_mb: float = 0.0


class WorkerPoolScheduler(QObject):
    job_updated = Signal(int)          # job_id -> UI debe refrescar esa fila
    jobs_changed = Signal()            # cambió la lista completa (add/remove)
    stats_tick = Signal(dict)          # snapshot de métricas para el dashboard
    job_failed = Signal(int, str)      # job_id, mensaje de error

    def __init__(self, db: Database, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.model_manager = model_manager
        self._workers: dict[int, _ActiveWorker] = {}
        self._next_worker_id = 0
        self._progress_queue: mp.Queue = mp.Queue()
        self._speed_history: dict[str, list[float]] = {}
        self._ram_history: list[tuple[float, float]] = []  # (timestamp, used_mb)
        self._throughput_history: list[tuple[float, float]] = []  # audio-seg transcritos acumulados

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._tick)
        self._poll_timer.start(500)  # 0.5s: procesa mensajes + decide escalado + progreso estimado

    # ---------------- API pública ----------------

    def start(self) -> None:
        self.db.reset_running_to_pending()
        self.jobs_changed.emit()

    def shutdown(self) -> None:
        for w in list(self._workers.values()):
            w.task_queue.put(None)
        for w in list(self._workers.values()):
            w.process.join(timeout=3.0)
            if w.process.is_alive():
                w.process.terminate()

    def enqueue_files(self, paths: list[Path], model_key: str, language: Optional[str], output_dir: Path) -> None:
        for p in paths:
            job = Job(
                id=None,
                source_path=str(p),
                display_name=p.name,
                model=model_key,
                language=language,
                output_dir=str(output_dir),
            )
            self.db.add_job(job)
        self.jobs_changed.emit()

    def cancel_job(self, job_id: int) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        if job.status == "pending":
            self.db.delete_job(job_id)
            self.jobs_changed.emit()
        # Si ya está corriendo, se deja terminar (matar un proceso a mitad de
        # transcripción no vale la pena para archivos individuales cortos).

    # ---------------- lógica interna ----------------

    def _max_parallel(self) -> int:
        return int(self.db.get_setting("max_parallel", "3"))

    def _ram_reserved_per_worker_mb(self) -> float:
        return float(self.db.get_setting("ram_reserved_per_worker_mb", "2200"))

    def _ram_safety_margin_mb(self) -> float:
        return float(self.db.get_setting("ram_safety_margin_mb", "1500"))

    def _tick(self) -> None:
        self._drain_progress_queue()
        self._maybe_scale_up()
        self._update_estimated_progress()
        self._emit_stats()

    def _drain_progress_queue(self) -> None:
        while not self._progress_queue.empty():
            msg = self._progress_queue.get()
            kind = msg[0]

            if kind == "model_loaded":
                _, worker_id, _model_key = msg
                # worker listo para recibir tareas

            elif kind == "duration":
                _, worker_id, job_id, duration = msg
                w = self._workers.get(worker_id)
                if w:
                    w.job_duration = duration
                    w.started_job_at = time.time()
                self.db.update_job(job_id, duration_seconds=duration, status="running", started_at=time.time())
                self.job_updated.emit(job_id)

            elif kind == "progress":
                _, worker_id, job_id, fraction, elapsed = msg
                self.db.update_job(job_id, progress=fraction, elapsed_seconds=elapsed)
                self.job_updated.emit(job_id)

            elif kind == "done":
                _, worker_id, job_id, result, elapsed, duration = msg
                self._handle_done(worker_id, job_id, result, elapsed, duration)

            elif kind == "error":
                _, worker_id, job_id, error_message = msg
                if job_id is not None:
                    self.db.update_job(job_id, status="error", error_message=error_message, finished_at=time.time())
                    self.job_failed.emit(job_id, error_message)
                    self.job_updated.emit(job_id)

            elif kind == "idle":
                _, worker_id = msg
                w = self._workers.get(worker_id)
                if w:
                    w.busy = False
                    w.current_job_id = None
                    w.started_job_at = None
                    w.job_duration = None

    def _handle_done(self, worker_id: int, job_id: int, result: dict, elapsed: float, duration: float) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        model_key = job.model
        speed = duration / elapsed if elapsed > 0 else None
        if speed:
            self._speed_history.setdefault(model_key, []).append(speed)

        try:
            output_dir = Path(job.output_dir or self.db.get_setting("output_dir"))
            paths = write_outputs(
                result=result,
                source_path=Path(job.source_path),
                output_dir=output_dir,
                model_key=model_key,
                elapsed_seconds=elapsed,
                duration_seconds=duration,
            )
            self.db.update_job(
                job_id,
                status="done",
                progress=1.0,
                elapsed_seconds=elapsed,
                speed_realtime=speed,
                finished_at=time.time(),
                result_json_path=str(paths["json"]),
            )
        except Exception as e:
            self.db.update_job(job_id, status="error", error_message=str(e), finished_at=time.time())
            self.job_failed.emit(job_id, str(e))

        now = time.time()
        prev_total = self._throughput_history[-1][1] if self._throughput_history else 0.0
        self._throughput_history.append((now, prev_total + duration))
        self._throughput_history = self._throughput_history[-240:]

        self.job_updated.emit(job_id)

    def _maybe_scale_up(self) -> None:
        pending = self.db.pending_jobs()
        if not pending:
            self._retire_idle_workers()
            return

        active_count = len(self._workers)
        if active_count >= self._max_parallel():
            self._assign_idle_workers(pending)
            return

        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        needed_mb = self._ram_reserved_per_worker_mb() + self._ram_safety_margin_mb()
        if available_mb < needed_mb:
            self._assign_idle_workers(pending)
            return

        # Hay RAM y cupo: primero intenta reusar un worker idle con el mismo modelo,
        # si no, lanza uno nuevo.
        next_job = pending[0]
        idle_worker = self._find_idle_worker(next_job.model)
        if idle_worker is not None:
            self._dispatch(idle_worker, next_job)
        else:
            self._spawn_worker(next_job)

    def _assign_idle_workers(self, pending: list[Job]) -> None:
        for job in pending:
            w = self._find_idle_worker(job.model)
            if w is not None:
                self._dispatch(w, job)

    def _find_idle_worker(self, model_key: str) -> Optional[_ActiveWorker]:
        for w in self._workers.values():
            if not w.busy and w.model_key == model_key:
                return w
        return None

    def _retire_idle_workers(self) -> None:
        # Mantiene los workers vivos (evita recargar el modelo constantemente);
        # no hace retiro agresivo. El shutdown() se encarga al cerrar la app.
        pass

    def _spawn_worker(self, job: Job) -> None:
        model_dir = str(self.model_manager.local_dir_for(job.model))
        worker_id = self._next_worker_id
        self._next_worker_id += 1

        task_queue: mp.Queue = mp.Queue()
        process = mp.Process(
            target=worker_main,
            args=(worker_id, job.model, model_dir, task_queue, self._progress_queue),
            daemon=True,
        )
        process.start()

        w = _ActiveWorker(worker_id=worker_id, process=process, task_queue=task_queue, model_key=job.model)
        self._workers[worker_id] = w
        self._dispatch(w, job)

    def _dispatch(self, w: _ActiveWorker, job: Job) -> None:
        w.busy = True
        w.current_job_id = job.id
        w.task_queue.put(TranscribeTask(job_id=job.id, source_path=job.source_path, language=job.language))
        self.db.update_job(job.id, status="running", started_at=time.time())
        self.job_updated.emit(job.id)

    def _update_estimated_progress(self) -> None:
        """Entre mensajes 'progress' reales del worker (poco frecuentes por ser
        una llamada bloqueante), estimamos el avance visual usando el tiempo
        transcurrido vs. la velocidad histórica observada del modelo."""
        now = time.time()
        for w in self._workers.values():
            if not w.busy or w.current_job_id is None or w.started_job_at is None or not w.job_duration:
                continue
            elapsed = now - w.started_job_at
            speeds = self._speed_history.get(w.model_key) or [DEFAULT_SPEED_GUESS.get(w.model_key, 2.0)]
            avg_speed = sum(speeds[-5:]) / len(speeds[-5:])
            expected_total = w.job_duration / avg_speed if avg_speed > 0 else w.job_duration
            fraction = min(elapsed / expected_total, 0.98) if expected_total > 0 else 0.0
            self.db.update_job(w.current_job_id, progress=fraction, elapsed_seconds=elapsed)
            self.job_updated.emit(w.current_job_id)

    def _emit_stats(self) -> None:
        vm = psutil.virtual_memory()
        now = time.time()

        worker_rows = []
        for w in self._workers.values():
            try:
                ram_mb = psutil.Process(w.process.pid).memory_info().rss / (1024 * 1024) if w.process.pid else 0.0
            except psutil.Error:
                ram_mb = 0.0
            w.ram_mb = ram_mb
            job = self.db.get_job(w.current_job_id) if w.current_job_id else None
            worker_rows.append({
                "worker_id": w.worker_id,
                "busy": w.busy,
                "model": w.model_key,
                "ram_mb": ram_mb,
                "job_id": w.current_job_id,
                "file_name": job.display_name if job else None,
                "progress": job.progress if job else 0.0,
                "speed": (job.duration_seconds / job.elapsed_seconds) if job and job.elapsed_seconds and job.duration_seconds else None,
            })

        self._ram_history.append((now, vm.used / (1024 * 1024)))
        self._ram_history = self._ram_history[-240:]  # ~2 min a 0.5s/tick

        jobs = self.db.list_jobs()
        counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
        for j in jobs:
            counts[j.status] = counts.get(j.status, 0) + 1

        self.stats_tick.emit({
            "timestamp": now,
            "ram_used_mb": vm.used / (1024 * 1024),
            "ram_available_mb": vm.available / (1024 * 1024),
            "ram_total_mb": vm.total / (1024 * 1024),
            "ram_history": list(self._ram_history),
            "throughput_history": list(self._throughput_history),
            "workers": worker_rows,
            "counts": counts,
        })
