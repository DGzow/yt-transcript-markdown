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
import re
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
import youtube_conta as conta

# Pasta onde toda transcrição gerada pela interface web é salva automaticamente.
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

# Subpasta de transcripts/ para vídeos colados como link direto (sem playlist).
# Playlists continuam ganhando uma pasta própria; os avulsos não ficam soltos na raiz.
PASTA_AVULSOS = "avulsos"

# A extração automática de cookies do Chrome/Edge morreu no Windows (Chrome 127+
# criptografa o banco com app-bound encryption; o yt-dlp responde "Failed to decrypt
# with DPAPI"). O caminho que ainda funciona é exportar um cookies.txt à mão.
DICA_COOKIES = (
    "Se você vê a transcrição no YouTube logado: instale a extensão "
    "\"Get cookies.txt LOCALLY\", entre no youtube.com em uma janela anônima, abra "
    "youtube.com/robots.txt na mesma aba, exporte o cookies.txt e feche a janela. "
    "Salve na pasta do app e escolha \"arquivo cookies.txt\" em Opções. "
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


DICA_BLOQUEIO = (
    "O YouTube está limitando o seu IP por excesso de requisições. Espere algumas horas "
    "antes de tentar de novo e transcreva menos vídeos por vez (aumente a pausa em Opções). "
    "O Whisper não resolve: ele também precisa baixar o áudio do YouTube."
)


def foi_bloqueio(detalhes: list[str]) -> bool:
    """True se as falhas registradas indicam bloqueio de IP / limite de requisições."""
    texto = " ".join(detalhes).lower()
    return bool(
        any(t in texto for t in ("ipblocked", "requestblocked", "too many requests"))
        or re.search(r"\b429\b", texto)
    )


def cookies_txt_disponivel() -> Path | None:
    """Procura um cookies.txt exportado do navegador, na pasta do app."""
    for nome in ("cookies.txt", "www.youtube.com_cookies.txt", "youtube.com_cookies.txt"):
        caminho = Path(__file__).parent / nome
        if caminho.is_file():
            return caminho
    return None


def html_opcao_cookies() -> str:
    """A opção "arquivo cookies.txt" do seletor. Vem SELECIONADA quando o arquivo existe:
    é o único jeito de cookies que funciona no Windows (Chrome/Edge criptografam os deles)."""
    arquivo = cookies_txt_disponivel()
    if arquivo:
        return f'<option value="arquivo" selected>arquivo cookies.txt ({arquivo.name})</option>'
    return '<option value="arquivo" disabled>arquivo cookies.txt (não encontrado)</option>'


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


def ids_ja_transcritos() -> set[str]:
    """IDs de vídeo que já têm um .md salvo em qualquer pasta de transcripts/.

    Os arquivos se chamam `titulo-do-video-<ID>.md`, e todo ID do YouTube tem 11
    caracteres, então os últimos 11 caracteres do nome (sem o .md) são o ID.
    Procura em todas as subpastas (rglob): um vídeo transcrito por outra playlist
    ou como link avulso também conta como feito.
    """
    if not TRANSCRIPTS_DIR.is_dir():
        return set()
    return {p.stem[-11:] for p in TRANSCRIPTS_DIR.rglob("*.md") if p.name != "README.md"}


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

    # Cookies do Chrome/Edge/Brave podem falhar antes mesmo de o YouTube ser
    # consultado. Uma playlist pública não precisa deles, então tenta de novo
    # anonimamente antes de mostrar erro ao usuário.
    erro_com_cookies = proc
    if proc.returncode != 0 and (arquivo_cookies or navegador_cookies):
        try:
            proc_sem_cookies = subprocess.run(
                list(base) + [
                    "--flat-playlist", "--dump-single-json", "--skip-download", url
                ],
                check=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
            if proc_sem_cookies.returncode == 0:
                proc = proc_sem_cookies
        except Exception:
            pass

    if proc.returncode != 0:
        detalhe = core._erro_ytdlp(
            erro_com_cookies, bool(arquivo_cookies or navegador_cookies)
        )
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

    # A tela usa isto para não oferecer de novo (por padrão) o que já foi transcrito.
    feitos = ids_ja_transcritos()
    for video in videos:
        video["ja_transcrito"] = video["video_id"] in feitos

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
        if foi_bloqueio(detalhes):
            dica = DICA_BLOQUEIO  # o motivo real; sugerir Whisper aqui só enganaria
        elif not whisper and audio.whisper_disponivel():
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
    # O nome é normalizado novamente no servidor: nunca aceitamos caminhos da tela.
    # Sem pasta de playlist, o vídeo vai para a subpasta dos avulsos.
    saved_folder = core.slugify(folder, max_len=100) if folder else PASTA_AVULSOS
    try:
        output_dir = TRANSCRIPTS_DIR / saved_folder
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
        "saved_folder": saved_folder,
        "save_error": save_error,
    }


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

INTERFACE_DIR = Path(__file__).parent / "interface"


def carregar_pagina() -> str:
    """Monta a página: o HTML-modelo com o CSS e o JavaScript embutidos.

    Os três arquivos ficam em interface/. O resultado é um documento único, então o
    servidor não precisa de rotas para arquivos estáticos. Lido a cada acesso: editar
    o CSS e recarregar o navegador já mostra a mudança, sem reiniciar o app.
    """
    html = (INTERFACE_DIR / "pagina.html").read_text(encoding="utf-8")
    css = (INTERFACE_DIR / "estilo.css").read_text(encoding="utf-8")
    js = (INTERFACE_DIR / "app.js").read_text(encoding="utf-8")
    return html.replace("<!--ESTILO-->", css).replace("<!--SCRIPT-->", js)


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

            html = (
                carregar_pagina().replace("<!--AVISO-->", aviso)
                .replace("<!--COOKIES_ARQUIVO-->", html_opcao_cookies())
                .replace("<!--WHISPER-->", bloco_whisper())
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/conta":
            self._json(conta.status())
        elif self.path == "/api/playlists":
            try:
                self._json({"ok": True, "playlists": conta.listar_playlists()})
            except PermissionError as exc:
                self._json({"ok": False, "error": str(exc)})
            except Exception as exc:  # falha de rede, cota estourada etc.
                self._json({"ok": False, "error": f"Não consegui listar as playlists: {exc}"})
        else:
            self._send(404, b"nao encontrado", "text/plain; charset=utf-8")

    def _json(self, dados: dict):
        """Atalho: responde um dicionário Python como JSON (equivale a json.dumps + _send)."""
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self._send(200, corpo, "application/json; charset=utf-8")

    def do_POST(self):
        if self.path == "/api/conta/entrar":
            print("  abrindo o login do Google no navegador...")
            try:
                conta.entrar()  # bloqueia até você aprovar (ou estourar o tempo limite)
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": f"Não consegui entrar: {exc}"})
            return
        if self.path == "/api/conta/sair":
            conta.sair()
            self._json({"ok": True})
            return

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
