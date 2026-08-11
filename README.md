# 🎙️ Voz a Texto

<p align="center">
  <strong>Transcripción de audio/vídeo 100% local en macOS, con la calidad de Whisper large-v3.</strong><br>
  Cola de trabajo persistente, paralelismo automático según RAM libre, y un dashboard en tiempo real
  para quien quiere ver los números detrás de cada transcripción.
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-black?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11-blue?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-en%20desarrollo-orange?style=flat-square">
</p>

---

## ¿Qué es esto?

Una app de escritorio nativa de macOS (PySide6) que corre **[Whisper](https://github.com/openai/whisper) `large-v3` / `large-v3-turbo`** de forma local usando **[MLX](https://github.com/ml-explore/mlx)**, el framework de Apple optimizado para Apple Silicon (M1/M2/M3). Nada de tu audio sale de tu Mac.

Pensada para quien necesita transcribir **muchos archivos** (clases, entrevistas, reuniones) con la mejor calidad posible, sin depender de servicios en la nube, y sin tener que lanzar comandos manualmente uno por uno.

## ✨ Características

- 🗂️ **Cola de trabajo persistente** — encola 5, 10 o más archivos por drag&drop; la app los procesa sola y la cola sobrevive a cerrar/reabrir (SQLite).
- ⚡ **Paralelismo automático e inteligente** — un scheduler monitorea la RAM disponible en tiempo real y decide cuándo lanzar una nueva instancia de transcripción, respetando un límite máximo ajustable (por defecto conservador, ya que la GPU/Metal se comparte entre procesos).
- 📦 **Gestión de modelos integrada** — descarga `large-v3` (máxima calidad) y `large-v3-turbo` (el mejor equilibrio velocidad/calidad) desde la propia app, con barra de progreso.
- 📊 **Dashboard para ingenieros** — gráficas en tiempo real de RAM usada/disponible, throughput acumulado, y tarjetas por instancia activa con archivo actual, % completado, velocidad (x tiempo real) y RAM consumida.
- 📝 **Salidas completas por archivo** — `.txt` (texto con puntuación), `.srt` (subtítulos con timestamps) y `.json` (segmentos + metadata: idioma detectado, duración, tiempo de proceso, factor de velocidad).
- 🌓 **Interfaz minimalista y oscura**, pensada para tener siempre a la vista qué está pasando sin ruido visual.

## 🖥️ Requisitos

- macOS 13+ en **Apple Silicon** (M1/M2/M3). MLX no corre en Intel.
- Python 3.11 (recomendado vía Homebrew: `brew install python@3.11`).
- ~2 GB libres para `large-v3-turbo`, ~3 GB para `large-v3` (se descargan bajo demanda desde la app).

## 🚀 Empezar

```bash
git clone https://github.com/JoseLuis0022/voz-a-texto-mlx.git
cd voz-a-texto-mlx

python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m app.main
```

Al abrir la app por primera vez, ve al panel **Modelos** y descarga `large-v3-turbo` (recomendado para empezar) y/o `large-v3` (máxima calidad). Luego arrastra tus archivos a la **Cola** y listo.

## 📦 Empaquetar como app standalone (.app)

```bash
./.venv/bin/pip install pyinstaller
./.venv/bin/pyinstaller packaging/VozATexto.spec --noconfirm
open "dist/Voz a Texto.app"
```

## 🏗️ Arquitectura

```
app/
├── main.py                    # entry point (QApplication + MainWindow)
├── data/
│   └── db.py                  # SQLite: cola de trabajo + configuración
├── core/
│   ├── model_manager.py       # descarga/gestión de modelos MLX (Hugging Face)
│   ├── transcriber_worker.py  # proceso hijo: carga el modelo una vez, transcribe en cadena
│   ├── scheduler.py           # decide paralelismo según RAM libre + traduce a señales Qt
│   └── outputs.py             # genera .txt / .srt / .json
├── ui/
│   ├── main_window.py
│   ├── queue_panel.py         # cola con drag&drop, progreso, selector de modelo
│   ├── dashboard_panel.py     # gráficas en tiempo real (pyqtgraph)
│   ├── model_panel.py         # descarga de modelos
│   ├── results_panel.py       # visor de transcripciones
│   └── preferences_dialog.py
└── resources/                 # estilos, iconos
```

### Cómo funciona el paralelismo

En vez de lanzar un proceso nuevo por cada archivo (pagando el costo de cargar el modelo cada vez), la app mantiene un **pool de procesos worker persistentes**: cada uno carga el modelo una sola vez y va tomando archivos de la cola en cadena. Cada ~0.5s, el scheduler:

1. Revisa la RAM disponible del sistema (`psutil`).
2. Si hay archivos pendientes, RAM de sobra, y el número de workers activos está por debajo del límite configurado → lanza una nueva instancia.
3. Si la RAM escasea, deja de escalar (sin matar lo que ya está corriendo).

> **Nota:** la GPU (Metal) es memoria unificada y se comparte entre procesos, así que el límite de paralelismo por defecto es conservador (2-3) aunque sobre RAM — más instancias no siempre significa más velocidad. Ajustable en Preferencias.

## 🗺️ Roadmap

- [ ] Icono de app (.icns) y firma de código para distribución sin advertencias de Gatekeeper
- [ ] Reordenar la cola por drag&drop
- [ ] Exportar a más formatos (VTT, DOCX)
- [ ] Detección de hablantes (diarización)

## 📄 Licencia

[MIT](LICENSE)
