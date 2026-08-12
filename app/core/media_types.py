"""Extensiones de archivo aceptadas como fuente para transcribir.

Los vídeos se aceptan igual que el audio: antes de transcribir, el worker
les extrae solo la pista de audio a un .wav temporal (ver
`app.core.transcriber_worker._extract_audio`) — el vídeo en sí nunca se
decodifica ni se toca más allá de eso.
"""

from __future__ import annotations

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".aiff", ".opus"}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".wmv", ".m4v", ".flv", ".3gp", ".mpg", ".mpeg",
}

MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
