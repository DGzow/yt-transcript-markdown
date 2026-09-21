#!/usr/bin/env python3
"""
yt_transcript_md.py — baixa a transcrição de vídeos do YouTube e salva em Markdown.

Uso rápido:
    python yt_transcript_md.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python yt_transcript_md.py URL1 URL2 URL3 -o ./transcricoes
    python yt_transcript_md.py --from-file lista.txt --lang pt en --no-timestamps

Dependências (instale pelo menos uma das duas primeiras):
    pip install youtube-transcript-api      # método principal, rápido
    pip install yt-dlp                      # fallback, mais resistente a bloqueios
    pip install faster-whisper              # último recurso: transcreve o áudio (--whisper)

Os três caminhos são tentados nessa ordem, e o Whisper só entra com --whisper,
porque ele é lento: baixa o áudio e transcreve na CPU da própria máquina.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Utilidades de URL / ID
# --------------------------------------------------------------------------- #

VERSAO = "2.1"

_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})"),
]


def extract_video_id(value: str) -> str | None:
    """Aceita URL em qualquer formato do YouTube ou o próprio ID de 11 chars."""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    for pattern in _ID_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    return None


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def slugify(text: str, max_len: int = 70) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "video"


def format_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# --------------------------------------------------------------------------- #
# Metadados (título, canal) — via oEmbed público, sem API key
# --------------------------------------------------------------------------- #


def fetch_metadata(video_id: str) -> dict:
    params = urllib.parse.urlencode({"url": watch_url(video_id), "format": "json"})
    url = f"https://www.youtube.com/oembed?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        return {
            "title": data.get("title", video_id),
            "channel": data.get("author_name", ""),
            "channel_url": data.get("author_url", ""),
        }
    except Exception:
        return {"title": video_id, "channel": "", "channel_url": ""}


# --------------------------------------------------------------------------- #
# Método 1: youtube-transcript-api (compatível com v0.6.x e v1.x)
# --------------------------------------------------------------------------- #


def fetch_via_api(video_id: str, languages: list[str]):
    """Retorna (snippets, idioma, erro). O erro nunca é engolido — ele explica a causa."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, None, "youtube-transcript-api não instalado (pip install youtube-transcript-api)"

    usa_api_nova = hasattr(YouTubeTranscriptApi, "fetch")

    def _snippets(fetched):
        return [
            {"text": s.text, "start": s.start, "duration": s.duration}
            if hasattr(s, "text") else dict(s)
            for s in fetched
        ]

    try:
        if usa_api_nova:
            api = YouTubeTranscriptApi()
            listagem = api.list(video_id)
        else:
            listagem = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {_resumo(exc)}"

    disponiveis = []
    try:
        disponiveis = [t.language_code for t in listagem]
    except Exception:
        pass

    # 1) idioma pedido; 2) qualquer legenda existente; 3) tradução automática
    tentativas = []
    try:
        tentativas.append(listagem.find_transcript(languages))
    except Exception:
        pass
    for t in listagem:
        if t not in tentativas:
            tentativas.append(t)

    ultimo_erro = None
    for transcript in tentativas:
        try:
            return _snippets(transcript.fetch()), transcript.language_code, None
        except Exception as exc:
            ultimo_erro = f"{type(exc).__name__}: {_resumo(exc)}"

    if not tentativas:
        return None, None, (
            "O vídeo não expõe nenhuma legenda para download."
            + (f" Idiomas listados: {', '.join(disponiveis)}." if disponiveis else "")
        )
    return None, None, ultimo_erro or "Falha desconhecida ao buscar a legenda."


def _resumo(exc: Exception) -> str:
    """Reduz as mensagens quilométricas da biblioteca a uma linha útil."""
    texto = " ".join(str(exc).split())
    if "blocking requests from your IP" in texto or "RequestBlocked" in type(exc).__name__:
        return ("o YouTube bloqueou este IP (excesso de requisições ou suspeita de robô). "
                "Espere algumas horas; se persistir, use um cookies.txt (--cookies).")
    if "age" in texto.lower() and "restrict" in texto.lower():
        return "vídeo com restrição de idade — precisa de cookies de uma conta logada."
    if "unavailable" in texto.lower():
        return "vídeo indisponível, privado ou removido."
    return texto[:220]


# --------------------------------------------------------------------------- #
# Método 2: yt-dlp (fallback) — baixa legendas .vtt e converte
# --------------------------------------------------------------------------- #

_VTT_TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_VTT_TAG = re.compile(r"<[^>]+>")


def _vtt_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _strip_overlap(previous: str, current: str) -> str:
    """Remove do início de `current` as palavras que já apareceram no fim de `previous`."""
    prev_words = previous.split()
    cur_words = current.split()
    max_overlap = min(len(prev_words), len(cur_words))
    for size in range(max_overlap, 0, -1):
        if prev_words[-size:] == cur_words[:size]:
            return " ".join(cur_words[size:])
    return current


def parse_vtt(content: str) -> list[dict]:
    """Converte VTT em snippets, removendo a duplicação típica de legenda automática."""
    snippets: list[dict] = []
    start = end = None
    buffer: list[str] = []

    def flush():
        nonlocal buffer, start, end
        if start is not None and buffer:
            text = _VTT_TAG.sub("", " ".join(buffer))
            text = re.sub(r"\s+", " ", text).strip()

            if text and snippets:
                last = snippets[-1]
                # legenda "rolling": a nova linha começa repetindo a anterior inteira
                if text.startswith(last["text"]) and len(text) > len(last["text"]):
                    last["text"] = text
                    last["duration"] = max((end or start) - last["start"], 0.0)
                    buffer = []
                    return
                if text == last["text"]:
                    buffer = []
                    return
                # sobreposição parcial de palavras entre uma linha e a seguinte
                text = _strip_overlap(last["text"], text)

            if text:
                snippets.append(
                    {"text": text, "start": start, "duration": max((end or start) - start, 0.0)}
                )
        buffer = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")):
            continue
        match = _VTT_TIME.search(line)
        if match:
            flush()
            start = _vtt_seconds(*match.groups()[:4])
            end = _vtt_seconds(*match.groups()[4:])
            continue
        if line.isdigit():
            continue
        buffer.append(line)
    flush()
    return snippets


def ytdlp_disponivel() -> bool:
    """Verdadeiro se der para chamar o yt-dlp — pelo .exe no PATH OU pelo módulo."""
    import importlib.util

    return bool(shutil.which("yt-dlp")) or importlib.util.find_spec("yt_dlp") is not None


def ytdlp_base_cmd() -> list[str] | None:
    """Comando-base do yt-dlp.

    O `pip install yt-dlp` nem sempre deixa um `yt-dlp.exe` no PATH (é o caso desta
    máquina: C:\\Python314\\Scripts só tem o pip). Procurar apenas o executável faz o
    app dizer "falta instalar" com o pacote instalado. Chamar pelo módulo sempre
    funciona quando o pacote existe, então ele é o caminho preferido.
    """
    import importlib.util

    if importlib.util.find_spec("yt_dlp") is not None:
        base = [sys.executable, "-m", "yt_dlp"]
    else:
        exe = shutil.which("yt-dlp")
        if not exe:
            return None
        base = [exe]

    # O YouTube esconde os formatos atrás de um desafio em JavaScript. Sem um runtime
    # habilitado, o yt-dlp responde "Requested format is not available" e aborta.
    # Por padrão ele só usa o `deno`; o `node` precisa ser pedido (e o pacote
    # `yt-dlp-ejs` traz o script que resolve o desafio).
    if shutil.which("node"):
        base += ["--js-runtimes", "node"]
    return base


def fetch_via_ytdlp(
    video_id: str,
    languages: list[str],
    cookies_from: str | None = None,
    cookies_file: str | None = None,
):
    """Retorna (snippets, idioma, erro). Aceita cookies (navegador ou arquivo) para driblar bloqueio."""
    base = ytdlp_base_cmd()
    if not base:
        return None, None, "yt-dlp não instalado (pip install yt-dlp)"

    sub_langs = ",".join(f"{lang}.*" for lang in languages) + ",en.*"
    with tempfile.TemporaryDirectory() as tmp:

        def montar(langs_arg: str) -> list[str]:
            cmd = list(base) + [
                "--skip-download",
                # Só queremos o texto: se nenhum formato de vídeo estiver disponível,
                # isso não pode impedir a gravação da legenda.
                "--ignore-no-formats-error",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs", langs_arg,
                "--sub-format", "vtt",
                "--convert-subs", "vtt",
                "-o", os.path.join(tmp, "%(id)s.%(ext)s"),
            ]
            if cookies_file:
                cmd += ["--cookies", cookies_file]
            elif cookies_from:
                cmd += ["--cookies-from-browser", cookies_from]
            cmd.append(watch_url(video_id))
            return cmd

        def rodar(cmd: list[str]):
            try:
                return subprocess.run(
                    cmd, check=False, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=300,
                ), None
            except subprocess.TimeoutExpired:
                return None, "yt-dlp demorou demais e foi interrompido."
            except Exception as exc:
                return None, f"não consegui executar o yt-dlp: {exc}"

        proc, falha = rodar(montar(sub_langs))
        if falha:
            return None, None, falha

        files = sorted(Path(tmp).glob("*.vtt"))

        # Nada nos idiomas pedidos: pode existir legenda em outro idioma. Tenta tudo
        # antes de desistir — melhor entregar em espanhol do que não entregar nada.
        if not files:
            saida = ((proc.stdout or "") + (proc.stderr or "")).lower()
            if "no subtitles for the requested languages" in saida:
                proc2, falha2 = rodar(montar("all"))
                if not falha2 and proc2 is not None:
                    proc = proc2
                    files = sorted(Path(tmp).glob("*.vtt"))

        if not files:
            return None, None, _erro_ytdlp(proc, bool(cookies_from or cookies_file))

        chosen = files[0]
        for lang in languages:
            for f in files:
                if f.name.split(".")[-2].startswith(lang):
                    chosen = f
                    break
            else:
                continue
            break

        lang_code = chosen.name.split(".")[-2]
        snippets = parse_vtt(chosen.read_text(encoding="utf-8", errors="ignore"))
        if not snippets:
            return None, None, "o arquivo de legenda veio vazio."
        return snippets, lang_code, None


def _erro_ytdlp(proc, tem_cookies: bool) -> str:
    """Traduz a saída do yt-dlp para uma linha que diz o que fazer a seguir."""
    saida = " ".join(((proc.stdout or "") + " " + (proc.stderr or "")).split()) if proc else ""
    baixo = saida.lower()

    if "dpapi" in baixo or "could not copy chrome cookie database" in baixo:
        return ("o Windows não deixa o yt-dlp ler os cookies do Chrome/Edge/Brave (a partir do "
                "Chrome 127 eles vêm criptografados). Exporte um cookies.txt com a extensão "
                "\"Get cookies.txt LOCALLY\", salve na pasta do app e escolha "
                "\"arquivo cookies.txt\" em COOKIES.")
    if "playlist does not exist" in baixo or "this playlist is private" in baixo:
        # Lista privada (ex.: Assistir mais tarde) sem sessão válida: o YouTube diz que
        # "não existe" em vez de pedir login.
        if tem_cookies:
            return ("o YouTube não reconheceu a sua sessão e tratou a lista privada como "
                    "inexistente. O cookies.txt provavelmente está incompleto ou vencido. "
                    "Exporte de novo: abra uma janela anônima, entre no youtube.com, abra "
                    "youtube.com/robots.txt na mesma aba, exporte e feche a janela.")
        return ("a lista é privada ou não existe. Para listas privadas, como a Assistir mais "
                "tarde, escolha \"arquivo cookies.txt\" em Opções (sessão logada).")
    if "could not find" in baixo and "cookies database" in baixo:
        return "não achei os cookies desse navegador nesta máquina — escolha outro ou use um cookies.txt."
    if "confirm your age" in baixo or "age-restricted" in baixo or "inappropriate" in baixo:
        return ("vídeo com restrição de idade — o YouTube só libera a legenda para conta "
                "logada. Use um cookies.txt de uma sessão logada.")
    if "sign in to confirm" in baixo or "not a bot" in baixo:
        return ("o YouTube pediu login por suspeita de robô. Use um cookies.txt de uma "
                "sessão logada.")
    if "drm protected" in baixo:
        return "vídeo protegido por DRM — não dá para extrair legenda."
    if "no subtitles for the requested languages" in baixo or "has no subtitles" in baixo:
        base = "este vídeo não publica nenhuma faixa de legenda (nem automática) para download."
        if not tem_cookies:
            base += " Se você vê a transcrição logado, tente com um cookies.txt."
        return base
    if "video unavailable" in baixo or "private video" in baixo:
        return "vídeo indisponível, privado ou removido."

    # Sobrou o cru: mostra só as linhas de ERROR, que é o que interessa.
    erros = [ln for ln in saida.split("ERROR:") if ln.strip()]
    if len(erros) > 1:
        return ("ERROR:" + erros[1])[:260]
    return saida[:260] or "o yt-dlp não encontrou arquivo de legenda."


# --------------------------------------------------------------------------- #
# Montagem do Markdown
# --------------------------------------------------------------------------- #


def clean(text: str) -> str:
    text = text.replace("\n", " ").replace("&#39;", "'").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<")
    return re.sub(r"\s+", " ", text).strip()


def build_paragraphs(snippets: list[dict], max_seconds: float, max_chars: int):
    """Agrupa falas curtas em parágrafos legíveis, quebrando em fim de frase."""
    paragraphs: list[tuple[float, str]] = []
    chunk: list[str] = []
    start: float | None = None

    for snip in snippets:
        text = clean(snip["text"])
        if not text:
            continue
        if start is None:
            start = float(snip["start"])
        chunk.append(text)
        elapsed = float(snip["start"]) + float(snip.get("duration", 0)) - start
        joined = " ".join(chunk)
        ends_sentence = bool(re.search(r"[.!?…]$", text))
        if (elapsed >= max_seconds and ends_sentence) or len(joined) >= max_chars:
            paragraphs.append((start, joined))
            chunk, start = [], None

    if chunk and start is not None:
        paragraphs.append((start, " ".join(chunk)))
    return paragraphs


def yaml_escape(value: str) -> str:
    return value.replace('"', '\\"')


def build_markdown(video_id, meta, snippets, language, source, args) -> str:
    paragraphs = build_paragraphs(snippets, args.chunk_seconds, args.chunk_chars)
    total = snippets[-1]["start"] + snippets[-1].get("duration", 0) if snippets else 0
    words = sum(len(p[1].split()) for p in paragraphs)

    lines = [
        "---",
        f'title: "{yaml_escape(meta["title"])}"',
        f'channel: "{yaml_escape(meta["channel"])}"',
        f"url: {watch_url(video_id)}",
        f"video_id: {video_id}",
        f"language: {language or 'desconhecido'}",
        f"duration: {format_ts(total)}",
        f"words: {words}",
        f"source: {source}",
        f"extracted_at: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        f"# {meta['title']}",
        "",
    ]

    header = []
    if meta["channel"]:
        header.append(f"**Canal:** {meta['channel']}")
    header.append(f"[Assistir no YouTube]({watch_url(video_id)})")
    lines += ["> " + " · ".join(header), "", "## Transcrição", ""]

    for start, text in paragraphs:
        if args.timestamps:
            link = f"{watch_url(video_id)}&t={int(start)}s"
            lines.append(f"**[{format_ts(start)}]({link})** {text}")
        else:
            lines.append(text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Fluxo principal
# --------------------------------------------------------------------------- #


def process(target: str, args) -> bool:
    video_id = extract_video_id(target)
    if not video_id:
        print(f"  ✗ Não consegui identificar o ID em: {target}", file=sys.stderr)
        return False

    meta = fetch_metadata(video_id)
    print(f"  → {meta['title']}")

    snippets, language, source = None, None, ""
    erros = []
    if args.method in ("auto", "api"):
        snippets, language, erro = fetch_via_api(video_id, args.lang)
        source = "youtube-transcript-api"
        if erro:
            erros.append(f"youtube-transcript-api → {erro}")
    if not snippets and args.method in ("auto", "yt-dlp"):
        snippets, language, erro = fetch_via_ytdlp(
            video_id, args.lang, args.cookies_from_browser, getattr(args, "cookies", None)
        )
        source = "yt-dlp"
        if erro:
            erros.append(f"yt-dlp → {erro}")

    # Terceiro caminho: sem legenda publicada, transcreve o áudio localmente.
    if not snippets and getattr(args, "whisper", None):
        import transcricao_audio

        print(f"    sem legenda — transcrevendo o áudio com Whisper ({args.whisper})...")
        marcos = [0.25, 0.5, 0.75]

        def progresso(fracao: float) -> None:
            while marcos and fracao >= marcos[0]:
                print(f"      {int(marcos.pop(0) * 100)}%")

        snippets, language, erro = transcricao_audio.fetch_via_whisper(
            video_id, args.lang, args.cookies_from_browser, getattr(args, "cookies", None),
            args.whisper, progresso,
        )
        source = f"whisper:{args.whisper}"
        if erro:
            erros.append(f"whisper → {erro}")

    if not snippets:
        print(f"  ✗ Não consegui a transcrição de {video_id}. Motivo:", file=sys.stderr)
        for e in erros:
            print(f"      {e}", file=sys.stderr)
        if not args.cookies_from_browser and not getattr(args, "cookies", None):
            print("      Dica: se o vídeo tem legenda no navegador logado, exporte um", file=sys.stderr)
            print("      cookies.txt e rode de novo com --cookies cookies.txt.", file=sys.stderr)
        return False

    markdown = build_markdown(video_id, meta, snippets, language, source, args)

    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(meta['title'])}-{video_id}.md"
    path = outdir / filename
    path.write_text(markdown, encoding="utf-8")
    print(f"  ✓ Salvo em {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Baixa transcrições do YouTube e salva em Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("urls", nargs="*", help="URLs ou IDs de vídeos do YouTube")
    parser.add_argument("--from-file", help="Arquivo .txt com uma URL por linha")
    parser.add_argument("-o", "--outdir", default="./transcricoes", help="Pasta de saída")
    parser.add_argument(
        "--lang", nargs="+", default=["pt", "pt-BR", "en"],
        help="Idiomas preferidos, em ordem (padrão: pt pt-BR en)",
    )
    parser.add_argument(
        "--method", choices=["auto", "api", "yt-dlp"], default="auto",
        help="Como buscar a legenda (padrão: auto, tenta os dois)",
    )
    parser.add_argument(
        "--cookies-from-browser", metavar="NAVEGADOR", default=None,
        help="Usa os cookies do navegador (chrome, firefox, edge, brave, safari...) "
             "para driblar o bloqueio do YouTube. Feche o navegador antes. "
             "No Windows, Chrome/Edge costumam falhar (DPAPI) — prefira --cookies.",
    )
    parser.add_argument(
        "--cookies", metavar="ARQUIVO", default=None,
        help="Arquivo cookies.txt (formato Netscape) exportado do navegador logado. "
             "É o caminho que funciona no Windows quando --cookies-from-browser falha.",
    )
    parser.add_argument(
        "--whisper", metavar="MODELO", nargs="?", const="small", default=None,
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Se não houver legenda, transcreve o áudio localmente com o Whisper "
             "(tiny, base, small, medium, large-v3; padrão small). "
             "Exige: pip install faster-whisper",
    )
    parser.add_argument(
        "--no-timestamps", dest="timestamps", action="store_false",
        help="Gera texto corrido, sem marcações de tempo",
    )
    parser.add_argument(
        "--chunk-seconds", type=float, default=45.0,
        help="Duração alvo de cada parágrafo, em segundos (padrão: 45)",
    )
    parser.add_argument(
        "--chunk-chars", type=int, default=700,
        help="Tamanho máximo de cada parágrafo, em caracteres (padrão: 700)",
    )
    args = parser.parse_args()

    targets = list(args.urls)
    if args.from_file:
        content = Path(args.from_file).read_text(encoding="utf-8")
        targets += [
            line.strip() for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    if not targets:
        parser.print_help()
        return 1

    print(f"Processando {len(targets)} vídeo(s)...\n")
    ok = 0
    for i, target in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {target}")
        if process(target, args):
            ok += 1
        print()

    print(f"Concluído: {ok}/{len(targets)} transcrição(ões) salva(s).")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
