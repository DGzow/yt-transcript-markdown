#!/usr/bin/env python3
"""
app.py — interface web local para o yt_transcript_md.py

Rode:
    python app.py

Abre em http://127.0.0.1:7860 — cole a URL do vídeo e pronto.
Sem dependências extras: usa só a biblioteca padrão do Python.
O arquivo yt_transcript_md.py precisa estar na mesma pasta.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

try:
    import yt_transcript_md as core
except ImportError:
    print(
        "Não encontrei yt_transcript_md.py.\n"
        "Coloque os dois arquivos na mesma pasta e rode de novo.",
        file=sys.stderr,
    )
    sys.exit(1)

import transcricao_audio as audio

# Pasta onde toda transcrição gerada pela interface web é salva automaticamente.
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

# A extração automática de cookies do Chrome/Edge morreu no Windows (Chrome 127+
# criptografa o banco com app-bound encryption; o yt-dlp responde "Failed to decrypt
# with DPAPI"). O caminho que ainda funciona é exportar um cookies.txt à mão.
DICA_COOKIES = (
    "Se você vê a transcrição no YouTube logado: instale a extensão "
    "\"Get cookies.txt LOCALLY\", abra o youtube.com logado, exporte o cookies.txt, "
    "salve na pasta do app e escolha \"arquivo cookies.txt\" em COOKIES. "
    "No Windows, ler cookies direto do Chrome/Edge não funciona mais."
)


# --------------------------------------------------------------------------- #
# Dependências
# --------------------------------------------------------------------------- #


def checar_dependencias() -> list[str]:
    """Devolve o nome dos pacotes que faltam neste interpretador.

    O yt-dlp é checado pelo MÓDULO, não pelo `yt-dlp.exe` no PATH: o pip nem sempre
    instala o executável (nesta máquina, C:\\Python314\\Scripts só tem o pip), e
    procurar só o .exe fazia o app pedir a instalação de um pacote já instalado.
    """
    import importlib.util

    faltando = []
    if importlib.util.find_spec("youtube_transcript_api") is None:
        faltando.append("youtube-transcript-api")
    if not core.ytdlp_disponivel():
        faltando.append("yt-dlp")
    return faltando


def bloco_whisper() -> str:
    """Monta a linha do Whisper na interface — ou o convite a instalá-lo."""
    if not audio.whisper_disponivel():
        return (
            '<p class="hint">Para transcrever vídeos <b>sem legenda nenhuma</b>, instale o '
            'Whisper (roda offline, na sua máquina):<br>'
            f'<code>{sys.executable} -m pip install faster-whisper</code></p>'
        )

    opcoes = "".join(
        f'<option value="{nome}"{" selected" if nome == audio.MODELO_PADRAO else ""}>'
        f"{nome} — {desc}</option>"
        for nome, desc in audio.MODELOS.items()
    )
    return (
        '<label class="switch">'
        '<input type="checkbox" id="wh">'
        '<span class="track"></span>'
        "<span>Transcrever o áudio se não houver legenda</span>"
        "</label>"
        '<div class="field">'
        '<span class="field-label">Modelo</span>'
        f'<select class="picker" id="whmodel">{opcoes}</select>'
        "</div>"
        '<p class="hint">Roda offline, sem enviar o áudio para lugar nenhum. É lento: '
        "conte alguns minutos por vídeo, e o primeiro uso ainda baixa o modelo. "
        "O andamento aparece no terminal do <b>app.py</b>.</p>"
    )


def cookies_txt_disponivel() -> Path | None:
    """Procura um cookies.txt exportado do navegador, na pasta do app."""
    for nome in ("cookies.txt", "www.youtube.com_cookies.txt", "youtube.com_cookies.txt"):
        caminho = Path(__file__).parent / nome
        if caminho.is_file():
            return caminho
    return None


def opcoes_cookies(cookies: str | None) -> tuple[str | None, str | None, str | None]:
    """Converte a escolha da tela nas opções usadas pelo yt-dlp."""
    if cookies == "arquivo":
        caminho = cookies_txt_disponivel()
        if caminho is None:
            return None, None, f"Não achei um cookies.txt em {Path(__file__).parent}."
        return str(caminho), None, None
    return None, cookies or None, None


def is_playlist_url(url: str) -> bool:
    """Distingue playlist de vídeo comum sem fazer uma chamada à rede."""
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
    except ValueError:
        return False
    return "list" in query or "/playlist" in parsed.path


def expand_target(url: str, cookies: str | None = None) -> dict:
    """Expande uma playlist em vídeos; um vídeo comum passa direto."""
    if not is_playlist_url(url):
        video_id = core.extract_video_id(url)
        if not video_id:
            return {"ok": False, "error": "Esse link não é de um vídeo ou playlist do YouTube."}
        return {
            "ok": True, "is_playlist": False, "title": "", "folder": None,
            "videos": [{"url": core.watch_url(video_id), "video_id": video_id, "title": ""}],
        }

    base = core.ytdlp_base_cmd()
    if not base:
        return {"ok": False, "error": "Para ler playlists, instale o yt-dlp."}

    arquivo_cookies, navegador_cookies, erro = opcoes_cookies(cookies)
    if erro:
        return {"ok": False, "error": erro, "dica": DICA_COOKIES}

    cmd = list(base) + ["--flat-playlist", "--dump-single-json", "--skip-download"]
    if arquivo_cookies:
        cmd += ["--cookies", arquivo_cookies]
    elif navegador_cookies:
        cmd += ["--cookies-from-browser", navegador_cookies]
    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "A leitura da playlist passou de 5 minutos e foi interrompida."}
    except Exception as exc:
        return {"ok": False, "error": f"Não consegui ler a playlist: {exc}"}

    if proc.returncode != 0:
        detalhe = core._erro_ytdlp(proc.stderr or proc.stdout)
        return {"ok": False, "error": "Não consegui abrir a playlist.", "detalhes": [detalhe]}

    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "O YouTube devolveu uma lista em formato inesperado."}
    if not isinstance(data, dict):
        return {"ok": False, "error": "O YouTube devolveu uma lista em formato inesperado."}

    videos = []
    seen = set()
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        video_id = core.extract_video_id(str(entry.get("id") or ""))
        if not video_id:
            video_id = core.extract_video_id(str(entry.get("url") or ""))
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        videos.append({
            "url": core.watch_url(video_id), "video_id": video_id,
            "title": str(entry.get("title") or video_id),
        })

    if not videos:
        return {"ok": False, "error": "A playlist não tem vídeos disponíveis para transcrever."}

    title = str(data.get("title") or data.get("playlist_title") or "playlist")
    playlist_id = data.get("id") or urllib.parse.parse_qs(
        urllib.parse.urlparse(url).query
    ).get("list", [""])[0]
    title_slug = core.slugify(str(title), max_len=75)
    id_slug = core.slugify(str(playlist_id), max_len=20) if playlist_id else ""
    folder = f"{title_slug}-{id_slug}" if id_slug else title_slug
    return {
        "ok": True, "is_playlist": True, "title": title, "folder": folder, "videos": videos,
    }


# --------------------------------------------------------------------------- #
# Lógica
# --------------------------------------------------------------------------- #


def transcribe(
    url: str,
    langs: list[str],
    timestamps: bool,
    cookies: str | None = None,
    whisper: str | None = None,
    folder: str | None = None,
) -> dict:
    video_id = core.extract_video_id(url)
    if not video_id:
        return {"ok": False, "error": "Esse link não é de um vídeo do YouTube. Confira e cole de novo."}

    meta = core.fetch_metadata(video_id)

    # "arquivo" = usar o cookies.txt da pasta do app; qualquer outro valor é navegador.
    arquivo_cookies, navegador_cookies, erro_cookies = opcoes_cookies(cookies)
    if erro_cookies:
        return {
            "ok": False,
            "video_id": video_id,
            "title": meta["title"],
            "error": "Não achei o cookies.txt.",
            "detalhes": [erro_cookies],
            "dica": DICA_COOKIES,
        }

    detalhes = []
    snippets, language, erro = core.fetch_via_api(video_id, langs)
    source = "youtube-transcript-api"
    if erro:
        detalhes.append(f"youtube-transcript-api → {erro}")
    if not snippets:
        snippets, language, erro = core.fetch_via_ytdlp(
            video_id, langs, navegador_cookies, arquivo_cookies
        )
        source = "yt-dlp"
        if erro:
            detalhes.append(f"yt-dlp → {erro}")

    # Terceiro caminho: sem legenda publicada, transcreve o áudio na própria máquina.
    if not snippets and whisper:
        print(f"    sem legenda — transcrevendo o áudio com Whisper ({whisper})...")

        marcos = [0.25, 0.5, 0.75]

        def progresso(fracao: float) -> None:
            while marcos and fracao >= marcos[0]:
                print(f"      {int(marcos.pop(0) * 100)}%")

        snippets, language, erro = audio.fetch_via_whisper(
            video_id, langs, navegador_cookies, arquivo_cookies, whisper, progresso
        )
        source = f"whisper:{whisper}"
        if erro:
            detalhes.append(f"whisper → {erro}")

    if not snippets:
        dica = ""
        if not whisper and audio.whisper_disponivel():
            dica = ("Este vídeo não tem legenda para baixar. Ligue "
                    "\"Transcrever o áudio\" aqui em cima para o Whisper gerar a "
                    "transcrição na sua máquina.")
        elif not arquivo_cookies:
            dica = DICA_COOKIES
        return {
            "ok": False,
            "video_id": video_id,
            "title": meta["title"],
            "error": "Não consegui baixar a legenda.",
            "detalhes": detalhes,
            "dica": dica,
        }

    args = SimpleNamespace(timestamps=timestamps, chunk_seconds=45.0, chunk_chars=700)
    markdown = core.build_markdown(video_id, meta, snippets, language, source, args)

    total = snippets[-1]["start"] + snippets[-1].get("duration", 0)
    words = sum(len(core.clean(s["text"]).split()) for s in snippets)
    filename = f"{core.slugify(meta['title'])}-{video_id}.md"

    saved_path = None
    save_error = None
    try:
        # O nome é normalizado novamente no servidor: nunca aceitamos caminhos da tela.
        saved_folder = core.slugify(folder, max_len=100) if folder else None
        output_dir = TRANSCRIPTS_DIR / saved_folder if saved_folder else TRANSCRIPTS_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(markdown, encoding="utf-8")
        saved_path = str(path)
    except Exception as exc:
        save_error = f"não consegui salvar em disco: {exc}"

    return {
        "ok": True,
        "video_id": video_id,
        "title": meta["title"],
        "channel": meta["channel"],
        "language": language or "?",
        "duration": core.format_ts(total),
        "words": words,
        "source": source,
        "markdown": markdown,
        "filename": filename,
        "saved_path": saved_path,
        "saved_folder": core.slugify(folder, max_len=100) if folder else None,
        "save_error": save_error,
    }


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcrição de vídeo em Markdown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=DM+Mono:wght@400;500&family=Karla:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#10131A;
    --ink-soft:#2A2F3C;
    --paper:#E4E7EC;
    --surface:#FFFFFF;
    --muted:#697086;
    --line:#CDD2DB;
    --cc-yellow:#F2D544;
    --cc-cyan:#5EC6D6;
    --danger:#C4453B;
    --radius:4px;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--paper);
    color:var(--ink);
    font-family:'Karla',system-ui,sans-serif;
    font-size:16px;
    line-height:1.55;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:940px;margin:0 auto;padding:48px 24px 96px}

  /* ---------- cabeçalho ---------- */
  .eyebrow{
    font-family:'DM Mono',monospace;
    font-size:11px;letter-spacing:.18em;text-transform:uppercase;
    color:var(--muted);margin:0 0 14px;
    display:flex;align-items:center;gap:10px;
  }
  .eyebrow::after{content:"";flex:1;height:1px;background:var(--line)}
  h1{
    font-family:'Archivo',sans-serif;font-weight:800;
    font-size:clamp(30px,5.2vw,52px);line-height:1.02;
    letter-spacing:-.02em;margin:0 0 12px;
  }
  .lede{color:var(--ink-soft);max-width:52ch;margin:0 0 34px;font-size:17px}

  /* ---------- barra de legenda (elemento assinatura) ---------- */
  .caption-bar{
    position:relative;background:var(--ink);border-radius:var(--radius);
    padding:32px 22px 18px;box-shadow:0 12px 30px -18px rgba(16,19,26,.75);
  }
  .cc-badge{
    position:absolute;top:12px;left:22px;
    font-family:'DM Mono',monospace;font-size:10px;font-weight:500;
    letter-spacing:.16em;color:var(--ink);background:var(--cc-yellow);
    padding:2px 7px;border-radius:2px;
  }
  .cc-badge.live{animation:pulse 1.1s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

  #urls{
    width:100%;border:0;outline:0;resize:none;background:transparent;
    color:#F7F8FA;font-family:'DM Mono',monospace;font-size:15px;line-height:1.75;
    min-height:27px;caret-color:var(--cc-yellow);
  }
  #urls::placeholder{color:#5B6376}
  #urls:focus-visible{outline:0}
  .caption-bar:focus-within{box-shadow:0 0 0 2px var(--cc-yellow),0 12px 30px -18px rgba(16,19,26,.75)}
  .scanline{height:2px;background:#242936;margin-top:14px;overflow:hidden}
  .scanline i{display:block;height:100%;width:34%;background:var(--cc-yellow);
    transform:translateX(-100%);}
  .scanline.on i{animation:scan 1.1s linear infinite}
  @keyframes scan{to{transform:translateX(300%)}}

  /* ---------- controles ---------- */
  .controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:18px}
  .field{display:flex;align-items:center;gap:8px}
  .field-label{
    font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.14em;
    text-transform:uppercase;color:var(--muted);
  }
  .chips{display:flex;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
  .chips button{
    font-family:'DM Mono',monospace;font-size:12px;letter-spacing:.06em;
    background:var(--surface);border:0;border-right:1px solid var(--line);
    padding:8px 13px;cursor:pointer;color:var(--ink-soft);
  }
  .chips button:last-child{border-right:0}
  .chips button[aria-pressed="true"]{background:var(--ink);color:var(--cc-yellow)}
  .chips button:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}

  .picker{
    font-family:'DM Mono',monospace;font-size:12px;color:var(--ink-soft);
    background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
    padding:8px 10px;cursor:pointer;
  }
  .picker:focus-visible{outline:2px solid var(--ink);outline-offset:2px}

  .err-detail{
    font-family:'DM Mono',monospace;font-size:11.5px;line-height:1.7;
    color:var(--muted);margin:10px 0 0;padding:10px 12px;
    background:#FBF3F2;border-left:2px solid var(--danger);
    white-space:pre-wrap;word-break:break-word;
  }
  .err-hint{font-size:13.5px;color:var(--ink-soft);margin:10px 0 0}

  .switch{display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
  .switch input{position:absolute;opacity:0;width:0;height:0}
  .track{width:38px;height:21px;border-radius:11px;background:#C2C8D2;
    border:1px solid var(--line);position:relative;transition:background .15s}
  .track::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;
    border-radius:50%;background:var(--surface);transition:transform .15s;
    box-shadow:0 1px 2px rgba(0,0,0,.25)}
  .switch input:checked + .track{background:var(--ink)}
  .switch input:checked + .track::after{transform:translateX(17px);background:var(--cc-yellow)}
  .switch input:focus-visible + .track{outline:2px solid var(--ink);outline-offset:2px}
  .switch span:last-child{font-size:14px;color:var(--ink-soft)}

  .go{
    margin-left:auto;font-family:'Archivo',sans-serif;font-weight:600;font-size:15px;
    background:var(--ink);color:var(--surface);border:0;border-radius:var(--radius);
    padding:12px 26px;cursor:pointer;transition:transform .1s,background .15s;
  }
  .go:hover:not(:disabled){background:#000}
  .go:active:not(:disabled){transform:translateY(1px)}
  .go:disabled{opacity:.45;cursor:not-allowed}
  .go:focus-visible{outline:2px solid var(--ink);outline-offset:3px}

  /* ---------- status ---------- */
  #status{
    font-family:'DM Mono',monospace;font-size:12.5px;color:var(--muted);
    margin-top:22px;min-height:20px;
  }
  #status b{color:var(--ink);font-weight:500}

  /* ---------- resultados ---------- */
  .results{margin-top:34px;display:flex;flex-direction:column;gap:18px}
  .card{
    background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
    overflow:hidden;animation:rise .28s ease-out;
  }
  @keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  .card-head{padding:18px 20px;border-bottom:1px solid var(--line)}
  .card-title{font-family:'Archivo',sans-serif;font-weight:600;font-size:18px;
    line-height:1.25;margin:0 0 8px;letter-spacing:-.01em}
  .meta{display:flex;flex-wrap:wrap;gap:6px 18px;
    font-family:'DM Mono',monospace;font-size:11.5px;color:var(--muted)}
  .meta b{color:var(--ink-soft);font-weight:500}
  .preview{
    margin:0;padding:18px 20px;max-height:300px;overflow:auto;
    background:#F7F8FA;border-bottom:1px solid var(--line);
    font-family:'DM Mono',monospace;font-size:12.5px;line-height:1.72;
    white-space:pre-wrap;word-break:break-word;color:var(--ink-soft);
  }
  .preview .tc{color:#1E7C8C;font-weight:500}
  .preview .fm{color:var(--muted)}
  .card-foot{display:flex;gap:10px;padding:14px 20px;flex-wrap:wrap}
  .btn{
    font-family:'Karla',sans-serif;font-size:14px;font-weight:500;
    background:var(--surface);color:var(--ink);border:1px solid var(--line);
    border-radius:var(--radius);padding:9px 16px;cursor:pointer;transition:border-color .15s;
  }
  .btn:hover{border-color:var(--ink)}
  .btn:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
  .btn.primary{background:var(--ink);color:var(--surface);border-color:var(--ink)}
  .card.error{border-color:var(--danger)}
  .card.error .card-head{border-bottom:0}
  .err{color:var(--danger);font-size:14.5px;margin:0}

  .warn{
    background:#FFF9E3;border:1px solid #E0CE7A;border-left:3px solid var(--cc-yellow);
    border-radius:var(--radius);padding:16px 18px;margin:0 0 26px;
  }
  .warn h2{font-family:'Archivo',sans-serif;font-size:15px;margin:0 0 6px;font-weight:600}
  .warn p{margin:0 0 10px;font-size:14.5px;color:var(--ink-soft)}
  .warn code{
    display:block;font-family:'DM Mono',monospace;font-size:12.5px;
    background:var(--ink);color:var(--cc-yellow);padding:11px 14px;
    border-radius:var(--radius);overflow-x:auto;white-space:nowrap;
  }
  .warn small{display:block;margin-top:9px;font-family:'DM Mono',monospace;
    font-size:11px;color:var(--muted);word-break:break-all}

  .empty{
    margin-top:34px;padding:34px 20px;text-align:center;color:var(--muted);
    border:1px dashed var(--line);border-radius:var(--radius);
  }
  .empty p{margin:0;font-size:14.5px}

  .bulk{display:flex;justify-content:flex-end;margin-top:4px}

  /* ---------- linha do Whisper ---------- */
  .whisper-row{margin-top:12px;padding-top:14px;border-top:1px dashed var(--line)}
  .whisper-row .hint{
    font-size:13px;color:var(--muted);margin:0;flex-basis:100%;
  }
  .whisper-row .picker:disabled{opacity:.4;cursor:not-allowed}
  .whisper-row code{
    font-family:'DM Mono',monospace;font-size:12px;
    background:var(--ink);color:var(--cc-yellow);padding:2px 6px;border-radius:2px;
  }

  footer{
    margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
    font-family:'DM Mono',monospace;font-size:11.5px;color:var(--muted);
    display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
  }

  .toast{
    position:fixed;bottom:26px;left:50%;transform:translateX(-50%) translateY(80px);
    background:var(--ink);color:var(--cc-yellow);
    font-family:'DM Mono',monospace;font-size:12.5px;letter-spacing:.05em;
    padding:11px 20px;border-radius:var(--radius);opacity:0;
    transition:transform .22s,opacity .22s;pointer-events:none;z-index:10;
  }
  .toast.show{transform:translateX(-50%) translateY(0);opacity:1}

  @media (max-width:640px){
    .wrap{padding:32px 16px 72px}
    .go{margin-left:0;width:100%}
    .controls{gap:12px}
  }
  @media (prefers-reduced-motion:reduce){
    *{animation:none!important;transition:none!important}
  }
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">roda na sua máquina</p>
  <h1>Transcrição de vídeo em Markdown</h1>
  <p class="lede">Cole o link de um vídeo ou playlist do YouTube. Você também pode usar um link por linha.</p>
  <!--AVISO-->

  <div class="caption-bar">
    <span class="cc-badge" id="badge">CC</span>
    <textarea id="urls" rows="1" spellcheck="false"
      placeholder="https://www.youtube.com/watch?v=... ou https://www.youtube.com/playlist?list=..."></textarea>
    <div class="scanline" id="scan"><i></i></div>
  </div>

  <div class="controls">
    <div class="field">
      <span class="field-label">Idioma</span>
      <div class="chips" id="langs" role="group" aria-label="Idioma da legenda">
        <button type="button" data-lang="pt" aria-pressed="true">PT</button>
        <button type="button" data-lang="en" aria-pressed="false">EN</button>
        <button type="button" data-lang="es" aria-pressed="false">ES</button>
        <button type="button" data-lang="auto" aria-pressed="false">QUALQUER</button>
      </div>
    </div>
    <div class="field">
      <span class="field-label">Cookies</span>
      <select class="picker" id="cookies" title="Empresta a sessão logada quando o YouTube esconde a legenda">
        <option value="">nenhum</option>
        <!--COOKIES_ARQUIVO-->
        <option value="chrome">chrome</option>
        <option value="firefox">firefox</option>
        <option value="edge">edge</option>
        <option value="brave">brave</option>
        <option value="opera">opera</option>
        <option value="safari">safari</option>
      </select>
    </div>
    <label class="switch">
      <input type="checkbox" id="ts" checked>
      <span class="track"></span>
      <span>Marcar tempos</span>
    </label>
    <button class="go" id="go">Gerar Markdown</button>
  </div>

  <div class="controls whisper-row"><!--WHISPER--></div>

  <p id="status"></p>
  <div class="bulk" id="bulk"></div>
  <div class="results" id="results"></div>

  <div class="empty" id="empty">
    <p>Nada aqui ainda. Cole um link acima para começar.</p>
  </div>

  <footer>
    <span>servidor local · 127.0.0.1</span>
    <span>legenda → markdown · v2.1</span>
  </footer>
</div>

<div class="toast" id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
const box = $('urls'), results = $('results'), statusEl = $('status');
let lang = 'pt', done = [];

// textarea que cresce conforme você cola
const grow = () => { box.style.height = 'auto'; box.style.height = box.scrollHeight + 'px'; };
box.addEventListener('input', grow);

$('langs').addEventListener('click', (e) => {
  const btn = e.target.closest('button'); if (!btn) return;
  lang = btn.dataset.lang;
  [...$('langs').children].forEach(b => b.setAttribute('aria-pressed', b === btn));
});

box.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run();
});
$('go').addEventListener('click', run);

// o seletor de modelo só faz sentido com o Whisper ligado
if ($('wh')) {
  const sync = () => { $('whmodel').disabled = !$('wh').checked; };
  $('wh').addEventListener('change', sync);
  sync();
}

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2000);
}

const esc = (s) => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function stripFrontmatter(md) {
  // o .md salvo mantém o frontmatter; aqui ele só atrapalharia a leitura
  const m = md.match(/^---\n[\s\S]*?\n---\n+/);
  return m ? md.slice(m[0].length) : md;
}

function highlight(md) {
  return esc(stripFrontmatter(md)).split('\n').map(l =>
    l.replace(/^\*\*\[([\d:]+)\]\([^)]+\)\*\*/, '<span class="tc">[$1]</span>')
  ).join('\n');
}

function langsFor(code) {
  if (code === 'auto') return ['pt', 'pt-BR', 'en', 'es'];
  if (code === 'pt') return ['pt', 'pt-BR'];
  return [code];
}

function download(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type: 'text/markdown;charset=utf-8'}));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}

function renderCard(data) {
  const card = document.createElement('div');
  card.className = 'card' + (data.ok ? '' : ' error');

  if (!data.ok) {
    const detalhes = (data.detalhes || []).length
      ? '<p class="err-detail">' + esc(data.detalhes.join('\n')) + '</p>' : '';
    const dica = data.dica ? '<p class="err-hint">' + esc(data.dica) + '</p>' : '';
    card.innerHTML = '<div class="card-head">' +
      '<h2 class="card-title">' + esc(data.title || 'Não deu para transcrever') + '</h2>' +
      '<p class="err">' + esc(data.error) + '</p>' + detalhes + dica + '</div>';
    results.appendChild(card);
    return;
  }

  card.innerHTML =
    '<div class="card-head">' +
      '<h2 class="card-title">' + esc(data.title) + '</h2>' +
      '<div class="meta">' +
        (data.channel ? '<span>canal <b>' + esc(data.channel) + '</b></span>' : '') +
        '<span>duração <b>' + esc(data.duration) + '</b></span>' +
        '<span>palavras <b>' + data.words.toLocaleString('pt-BR') + '</b></span>' +
        '<span>idioma <b>' + esc(data.language) + '</b></span>' +
        '<span>arquivo <b>' + esc(data.filename) + '</b></span>' +
        (data.saved_path
          ? '<span>salvo em <b>transcripts/' + (data.saved_folder ? esc(data.saved_folder) + '/' : '') + '</b></span>'
          : '<span style="color:var(--danger)">não salvou automaticamente</span>') +
      '</div>' +
    '</div>' +
    '<pre class="preview">' + highlight(data.markdown) + '</pre>' +
    '<div class="card-foot">' +
      '<button class="btn primary" data-act="dl">Baixar .md</button>' +
      '<button class="btn" data-act="copy">Copiar</button>' +
      '<button class="btn" data-act="open">Abrir no YouTube</button>' +
    '</div>';

  card.querySelector('[data-act="dl"]').onclick = () => {
    download(data.filename, data.markdown); toast('Arquivo baixado');
  };
  card.querySelector('[data-act="copy"]').onclick = async () => {
    await navigator.clipboard.writeText(data.markdown); toast('Markdown copiado');
  };
  card.querySelector('[data-act="open"]').onclick = () => {
    window.open('https://www.youtube.com/watch?v=' + data.video_id, '_blank');
  };

  results.appendChild(card);
}

function renderBulk() {
  const bulk = $('bulk'); bulk.innerHTML = '';
  if (done.length < 2) return;
  const b = document.createElement('button');
  b.className = 'btn'; b.textContent = 'Baixar todos (' + done.length + ')';
  b.onclick = () => {
    done.forEach((d, i) => setTimeout(() => download(d.filename, d.markdown), i * 350));
    toast('Baixando ' + done.length + ' arquivos');
  };
  bulk.appendChild(b);
}

async function run() {
  const inputs = box.value.split('\n').map(s => s.trim()).filter(Boolean);
  if (!inputs.length) { box.focus(); toast('Cole um link primeiro'); return; }

  $('go').disabled = true;
  $('scan').classList.add('on');
  $('badge').classList.add('live');
  $('empty').style.display = 'none';
  results.innerHTML = ''; done = []; renderBulk();

  const wh = $('wh') && $('wh').checked ? $('whmodel').value : null;

  // Expande cada playlist antes de começar, para mostrar o total real de vídeos.
  const jobs = [], seen = new Set();
  for (let i = 0; i < inputs.length; i++) {
    statusEl.innerHTML = 'lendo link <b>' + (i + 1) + '/' + inputs.length + '</b> — ' +
      esc(inputs[i].slice(0, 60));
    try {
      const res = await fetch('/api/expand', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: inputs[i], cookies: $('cookies').value})
      });
      const expanded = await res.json();
      if (!expanded.ok) { renderCard(expanded); continue; }
      for (const video of expanded.videos) {
        const key = video.video_id + '|' + (expanded.folder || '');
        if (seen.has(key)) continue;
        seen.add(key);
        jobs.push({url: video.url, video_id: video.video_id, title: video.title,
          folder: expanded.folder, playlist_title: expanded.title});
      }
    } catch (err) {
      renderCard({ok: false, error: 'O servidor local não respondeu ao ler a playlist.'});
    }
  }

  if (!jobs.length) {
    $('go').disabled = false;
    $('scan').classList.remove('on'); $('badge').classList.remove('live');
    statusEl.textContent = 'nenhum vídeo encontrado'; return;
  }

  for (let i = 0; i < jobs.length; i++) {
    statusEl.innerHTML = 'buscando legenda <b>' + (i + 1) + '/' + jobs.length + '</b> — ' +
      esc((jobs[i].title || jobs[i].url).slice(0, 60)) +
      (wh ? '<br>sem legenda, o Whisper assume — acompanhe o andamento no terminal' : '');
    try {
      const res = await fetch('/api/transcript', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: jobs[i].url, langs: langsFor(lang), folder: jobs[i].folder,
          timestamps: $('ts').checked, cookies: $('cookies').value, whisper: wh})
      });
      const data = await res.json();
      renderCard(data);
      if (data.ok) done.push(data);
      renderBulk();
    } catch (err) {
      renderCard({ok: false, error: 'O servidor local não respondeu. Confira o terminal onde o app.py está rodando.'});
    }
  }

  $('go').disabled = false;
  $('scan').classList.remove('on');
  $('badge').classList.remove('live');
  statusEl.innerHTML = done.length
    ? '<b>' + done.length + '</b> de <b>' + jobs.length + '</b> pronto' + (done.length > 1 ? 's' : '') + ' — salvos em transcripts/'
    : 'nenhuma legenda encontrada';
  if (!results.children.length) $('empty').style.display = '';
}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Servidor
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):  # silencia o log padrão, barulhento demais
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            faltando = checar_dependencias()
            if faltando:
                aviso = (
                    '<div class="warn"><h2>Falta instalar: ' + ", ".join(faltando) + '</h2>'
                    '<p>Sem esses pacotes nenhum vídeo é transcrito. Rode no terminal e '
                    'reinicie o servidor:</p>'
                    '<code>' + sys.executable + ' -m pip install ' + " ".join(faltando) + '</code>'
                    '<small>usando este Python: ' + sys.executable + '</small></div>'
                )
            else:
                aviso = ""

            arquivo = cookies_txt_disponivel()
            if arquivo:
                opcao = f'<option value="arquivo">arquivo cookies.txt ({arquivo.name})</option>'
            else:
                opcao = ('<option value="arquivo" disabled>arquivo cookies.txt '
                         '(não encontrado)</option>')

            html = (
                PAGE.replace("<!--AVISO-->", aviso)
                .replace("<!--COOKIES_ARQUIVO-->", opcao)
                .replace("<!--WHISPER-->", bloco_whisper())
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"nao encontrado", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path not in ("/api/transcript", "/api/expand"):
            self._send(404, b"{}", "application/json")
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"ok": False, "error": "Pedido inválido."}).encode(), "application/json")
            return

        url = (payload.get("url") or "").strip()
        cookies = payload.get("cookies") or None

        if self.path == "/api/expand":
            print(f"  lendo link: {url}")
            try:
                result = expand_target(url, cookies)
            except Exception as exc:
                result = {"ok": False, "error": f"Erro inesperado ao ler o link: {exc}"}
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        langs = payload.get("langs") or ["pt", "pt-BR", "en"]
        timestamps = bool(payload.get("timestamps", True))
        whisper = payload.get("whisper") or None
        folder = payload.get("folder") or None
        if whisper and whisper not in audio.MODELOS:
            whisper = audio.MODELO_PADRAO

        print(f"  processando: {url}")
        try:
            result = transcribe(url, langs, timestamps, cookies, whisper, folder)
        except Exception as exc:  # nunca derruba o servidor
            result = {"ok": False, "error": f"Erro inesperado: {exc}"}

        if result.get("ok"):
            if result.get("saved_path"):
                print(f"    ok — salvo em {result['saved_path']}")
            else:
                print(f"    ok — mas não salvou no disco: {result.get('save_error', '')}")
        else:
            print(f"    falhou: {result.get('error', '')[:70]}")
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interface web local para transcrever vídeos do YouTube.")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador sozinho")
    args = parser.parse_args()

    address = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    print(f"\n  Transcrição de vídeo em Markdown — versão {getattr(core, 'VERSAO', '?')}")
    print(f"  Aberto em {address}")
    print(f"  Ctrl+C para encerrar.\n")

    faltando = checar_dependencias()
    if faltando:
        print(f"  ATENÇÃO: falta instalar {', '.join(faltando)}.")
        print(f"  Rode:  {sys.executable} -m pip install {' '.join(faltando)}")
        print(f"  (depois reinicie este servidor)\n")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(address)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
