#!/usr/bin/env python3
"""
transcricao_audio.py — último recurso: transcreve o ÁUDIO do vídeo com Whisper.

Entra em cena quando o vídeo não publica faixa de legenda nenhuma (nem automática),
caso em que a `youtube-transcript-api` responde `TranscriptsDisabled` e o yt-dlp
responde `has no subtitles`. Aqui não há legenda para baixar: o áudio é baixado e
transcrito localmente, sem enviar nada para fora da máquina.

Dependências:
    pip install faster-whisper      # traz junto o PyAV, que decodifica o áudio

O ffmpeg do sistema NÃO é necessário: o áudio é baixado no formato original
(m4a/webm, sem pós-processamento) e o PyAV decodifica direto.

O modelo é baixado do Hugging Face na primeira execução e fica em cache
(~/.cache/huggingface). "small" pesa ~500 MB; "medium", ~1,5 GB.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import yt_transcript_md as core

# Modelos oferecidos, do mais rápido ao mais preciso. O tempo é uma estimativa grosseira
# para CPU, em múltiplos da duração do vídeo (8 min de vídeo × fator = tempo de espera).
MODELOS = {
    "tiny": "mais rápido, erra bastante",
    "base": "rápido",
    "small": "equilíbrio (padrão)",
    "medium": "preciso, lento",
    "large-v3": "o melhor, bem lento",
}
MODELO_PADRAO = "small"

# Carregar o modelo custa segundos e memória; entre um vídeo e outro ele é reaproveitado.
_cache_modelo: dict[tuple[str, str, str], object] = {}


def whisper_disponivel() -> bool:
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def _dispositivo() -> tuple[str, str]:
    """Escolhe entre GPU e CPU. `int8` na CPU é o que torna a espera suportável."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _carregar_modelo(nome: str):
    from faster_whisper import WhisperModel

    device, compute_type = _dispositivo()
    chave = (nome, device, compute_type)
    if chave not in _cache_modelo:
        _cache_modelo[chave] = WhisperModel(nome, device=device, compute_type=compute_type)
    return _cache_modelo[chave]


# --------------------------------------------------------------------------- #
# Download do áudio
# --------------------------------------------------------------------------- #


def baixar_audio(
    video_id: str,
    destino: Path,
    cookies_from: str | None = None,
    cookies_file: str | None = None,
) -> tuple[Path | None, str | None]:
    """Baixa só a trilha de áudio, no formato original (sem exigir ffmpeg)."""
    base = core.ytdlp_base_cmd()
    if not base:
        return None, "yt-dlp não instalado (pip install yt-dlp)"

    cmd = list(base) + [
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "--no-playlist",
        "-o", os.path.join(str(destino), "%(id)s.%(ext)s"),
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    elif cookies_from:
        cmd += ["--cookies-from-browser", cookies_from]
    cmd.append(core.watch_url(video_id))

    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
    except subprocess.TimeoutExpired:
        return None, "o download do áudio passou de 15 minutos e foi interrompido."
    except Exception as exc:
        return None, f"não consegui executar o yt-dlp: {exc}"

    arquivos = [p for p in destino.iterdir() if p.is_file()]
    if not arquivos:
        return None, core._erro_ytdlp(proc, bool(cookies_from or cookies_file))
    return max(arquivos, key=lambda p: p.stat().st_size), None


# --------------------------------------------------------------------------- #
# Transcrição
# --------------------------------------------------------------------------- #


def _idioma_whisper(languages: list[str]) -> str | None:
    """Converte a lista do app ('pt', 'pt-BR', ...) no código de 2 letras do Whisper.

    Uma lista com mais de um idioma-raiz significa "qualquer um" na interface, e aí é
    melhor deixar o Whisper detectar do que forçar o primeiro da lista.
    """
    raizes = []
    for lang in languages or []:
        raiz = lang.split("-")[0].lower()
        if raiz and raiz not in raizes:
            raizes.append(raiz)
    return raizes[0] if len(raizes) == 1 else None


def transcrever_audio(
    caminho: Path,
    languages: list[str],
    modelo: str = MODELO_PADRAO,
    progresso=None,
) -> tuple[list[dict] | None, str | None, str | None]:
    """Retorna (snippets, idioma, erro) no mesmo formato dos outros métodos."""
    if not whisper_disponivel():
        return None, None, "faster-whisper não instalado (pip install faster-whisper)"
    if modelo not in MODELOS:
        modelo = MODELO_PADRAO

    try:
        model = _carregar_modelo(modelo)
    except Exception as exc:
        return None, None, f"não consegui carregar o modelo '{modelo}': {exc}"

    try:
        segmentos, info = model.transcribe(
            str(caminho),
            language=_idioma_whisper(languages),
            vad_filter=True,  # pula silêncio: menos alucinação e menos tempo de CPU
            beam_size=5,
            condition_on_previous_text=False,  # evita o loop de repetição em áudio longo
        )
    except Exception as exc:
        return None, None, f"o Whisper falhou ao ler o áudio: {exc}"

    total = getattr(info, "duration", 0) or 0
    snippets: list[dict] = []
    try:
        for seg in segmentos:  # gerador: a transcrição só acontece aqui
            texto = (seg.text or "").strip()
            if texto:
                snippets.append(
                    {"text": texto, "start": seg.start, "duration": max(seg.end - seg.start, 0.0)}
                )
            if progresso and total:
                progresso(min(seg.end / total, 1.0))
    except Exception as exc:
        if not snippets:
            return None, None, f"a transcrição foi interrompida: {exc}"

    if not snippets:
        return None, None, "o Whisper não encontrou fala no áudio."
    return snippets, getattr(info, "language", None), None


def fetch_via_whisper(
    video_id: str,
    languages: list[str],
    cookies_from: str | None = None,
    cookies_file: str | None = None,
    modelo: str = MODELO_PADRAO,
    progresso=None,
) -> tuple[list[dict] | None, str | None, str | None]:
    """Baixa o áudio e transcreve. Retorna (snippets, idioma, erro)."""
    if not whisper_disponivel():
        return None, None, "faster-whisper não instalado (pip install faster-whisper)"

    with tempfile.TemporaryDirectory() as tmp:
        audio, erro = baixar_audio(video_id, Path(tmp), cookies_from, cookies_file)
        if erro:
            return None, None, f"não consegui baixar o áudio: {erro}"
        return transcrever_audio(audio, languages, modelo, progresso)
