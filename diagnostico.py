#!/usr/bin/env python3
"""
diagnostico.py — descobre por que a transcrição de um vídeo não foi baixada.

Uso:
    python diagnostico.py "https://www.youtube.com/watch?v=SEU_VIDEO"

Mostra o erro real (sem esconder atrás de mensagem genérica), lista as legendas
que existem no vídeo e testa cada caminho de download separadamente.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import yt_transcript_md as core
except ImportError:
    print("Coloque diagnostico.py na mesma pasta do yt_transcript_md.py.")
    sys.exit(1)


def linha(titulo: str):
    print(f"\n{'─' * 68}\n{titulo}\n{'─' * 68}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    alvo = sys.argv[1]
    video_id = core.extract_video_id(alvo)
    if not video_id:
        print(f"Não consegui extrair o ID do vídeo de: {alvo}")
        return 1

    print(f"\nPython em uso: {sys.executable}")
    print(f"Vídeo: {video_id}")
    meta = core.fetch_metadata(video_id)
    print(f"Título: {meta['title']}")
    print(f"Canal: {meta['channel'] or '(não identificado)'}")

    # ------------------------------------------------------------------ #
    linha("1. Biblioteca instalada?")
    try:
        import youtube_transcript_api
        try:
            from importlib.metadata import version as _versao
            versao = _versao("youtube-transcript-api")
        except Exception:
            versao = getattr(youtube_transcript_api, "__version__", "versão desconhecida")
        print(f"  ok  youtube-transcript-api {versao}")
    except ImportError:
        print("  --  youtube-transcript-api NÃO instalado")
        youtube_transcript_api = None

    # O pip nem sempre deixa um yt-dlp.exe no PATH; procurar só o executável dá
    # "NÃO instalado" com o pacote instalado. Vale o módulo.
    tem_ytdlp = core.ytdlp_disponivel()
    onde = shutil.which("yt-dlp") or f"módulo, via {sys.executable} -m yt_dlp"
    print(f"  {'ok' if tem_ytdlp else '--'}  yt-dlp {'em ' + onde if tem_ytdlp else 'NÃO instalado'}")

    try:
        import transcricao_audio

        tem_whisper = transcricao_audio.whisper_disponivel()
    except ImportError:
        tem_whisper = False
    print(f"  {'ok' if tem_whisper else '--'}  faster-whisper "
          f"{'instalado (fallback de áudio disponível)' if tem_whisper else 'NÃO instalado (opcional)'}")

    faltando = []
    if not youtube_transcript_api:
        faltando.append("youtube-transcript-api")
    if not tem_ytdlp:
        faltando.append("yt-dlp")

    if faltando:
        cmd = [sys.executable, "-m", "pip", "install", *faltando]
        print(f"\n  Falta instalar: {', '.join(faltando)}")
        print(f"  Comando exato para ESTE Python:")
        print(f"      {' '.join(cmd)}")

        if "--instalar" in sys.argv:
            print("\n  Instalando agora...\n")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            saida = proc.stdout + proc.stderr
            print(saida[-1500:])

            # Debian/Ubuntu bloqueiam pip no Python do sistema (PEP 668)
            if proc.returncode != 0 and "externally-managed-environment" in saida:
                print("\n  O sistema bloqueou a instalação no Python global (proteção do Linux).")
                print("  Tentando de novo com --break-system-packages...\n")
                proc = subprocess.run([*cmd, "--break-system-packages"],
                                      capture_output=True, text=True)
                print((proc.stdout + proc.stderr)[-800:])

            if proc.returncode == 0:
                print("\n  Instalado. Rode o diagnóstico de novo (sem --instalar)")
                print("  e reinicie o app.py.")
                return 0

            print("\n  A instalação NÃO funcionou. Alternativa mais segura — ambiente isolado:")
            print(f"      {sys.executable} -m venv .venv")
            print("      source .venv/bin/activate      (no Windows: .venv\\Scripts\\activate)")
            print("      pip install youtube-transcript-api yt-dlp")
            print("      python app.py")
            return 1
        else:
            print("\n  Ou rode este mesmo diagnóstico com --instalar que eu instalo:")
            print(f"      {sys.executable} diagnostico.py \"{alvo}\" --instalar")
            # se ao menos uma existe, seguimos testando com ela
            if not youtube_transcript_api and not tem_ytdlp:
                print("\n  Sem nenhum dos dois, os passos seguintes não têm o que testar.")
                return 1
            print("  Seguindo com o que está disponível...")

    # ------------------------------------------------------------------ #
    linha("2. Quais legendas o vídeo tem?")
    if youtube_transcript_api:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            api = YouTubeTranscriptApi()
            listagem = api.list(video_id) if hasattr(api, "list") else YouTubeTranscriptApi.list_transcripts(video_id)
            achou = False
            for t in listagem:
                achou = True
                tipo = "automática" if t.is_generated else "manual"
                print(f"  • {t.language_code:<8} {t.language}  ({tipo})")
            if not achou:
                print("  Nenhuma legenda listada.")
        except Exception as exc:
            print(f"  ERRO AO LISTAR: {type(exc).__name__}")
            print(f"  {str(exc).strip()[:900]}")
    else:
        print("  (pulado — biblioteca não instalada)")

    # ------------------------------------------------------------------ #
    linha("3. Tentando baixar via youtube-transcript-api")
    snippets, lang, erro = core.fetch_via_api(video_id, ["pt", "pt-BR", "en"])
    if snippets:
        print(f"  ok  {len(snippets)} trechos em '{lang}'")
        print(f"      primeiro: {core.clean(snippets[0]['text'])[:70]}")
    else:
        print(f"  falhou: {erro}")

    # ------------------------------------------------------------------ #
    linha("4. Tentando baixar via yt-dlp")
    if not tem_ytdlp:
        print("  yt-dlp não instalado — instale com: pip install yt-dlp")
    else:
        snippets2, lang2, erro2 = core.fetch_via_ytdlp(video_id, ["pt", "pt-BR", "en"])
        if snippets2:
            print(f"  ok  {len(snippets2)} trechos em '{lang2}'")
        else:
            print(f"  falhou: {erro2}")

            print("\n  Saída bruta do yt-dlp (para inspeção):")
            proc = subprocess.run(
                core.ytdlp_base_cmd() + ["--list-subs", core.watch_url(video_id)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
            for linha_txt in (proc.stdout + proc.stderr).splitlines()[:25]:
                print(f"    {linha_txt}")

    # ------------------------------------------------------------------ #
    linha("5. Se nada funcionou: use os cookies do seu navegador")
    print("""
  Se você consegue ver a transcrição logado no navegador mas o script não,
  o YouTube está tratando o script como robô. A solução é emprestar os
  cookies da sua sessão:

      python yt_transcript_md.py "URL" --cookies-from-browser chrome

  Troque 'chrome' por firefox, edge, brave, opera, safari ou vivaldi.
  Feche o navegador antes de rodar — o Chrome trava o arquivo de cookies
  enquanto está aberto.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
