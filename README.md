# YouTube Transcript to Markdown

Aplicativo local para transformar vídeos e playlists do YouTube em arquivos
Markdown. Cada vídeo gera um `.md` com metadados, texto organizado em parágrafos
e marcações de tempo clicáveis.

## Recursos

- Vídeos individuais ou playlists completas pela interface web.
- Uma subpasta própria em `transcripts/` para cada playlist.
- Legendas públicas via `youtube-transcript-api` e `yt-dlp`.
- Transcrição de áudio sem legenda com Whisper, opcional e executado localmente.
- Preferência de idioma, timestamps, cookies de sessão e processamento em fila.
- CLI para vídeos individuais e listas de URLs.

## Requisitos

- Python 3.10 ou mais recente.
- Conexão com o YouTube para obter metadados, legendas ou áudio.
- `faster-whisper` somente para vídeos que não oferecem nenhuma legenda.

## Instalação

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No Linux ou macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Para habilitar também a transcrição de áudio com Whisper:

```bash
python -m pip install -r requirements-whisper.txt
```

## Uso pela interface

```bash
python app.py
```

O navegador abre em [http://127.0.0.1:7860](http://127.0.0.1:7860).

1. Cole o link de um vídeo ou playlist.
2. Escolha idioma, timestamps e, se necessário, cookies ou Whisper.
3. Clique em **Gerar Markdown**.

Vídeos avulsos são gravados diretamente em `transcripts/`. Para playlists, o app
cria uma pasta no formato:

```text
transcripts/
└── titulo-da-playlist-PLxxxx/
    ├── primeiro-video-ID.md
    └── segundo-video-ID.md
```

## Uso pela linha de comando

Um vídeo:

```bash
python yt_transcript_md.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Vários links em um arquivo, um por linha:

```bash
python yt_transcript_md.py --from-file lista.txt --lang pt en --no-timestamps
```

Escolhendo a pasta de saída e habilitando o Whisper:

```bash
python yt_transcript_md.py URL -o ./transcricoes --whisper small
```

## Como a transcrição é obtida

O app tenta estes caminhos em ordem:

| Ordem | Método | Uso |
|---:|---|---|
| 1 | `youtube-transcript-api` | Legenda pública; normalmente é o caminho mais rápido. |
| 2 | `yt-dlp` | Outras faixas de legenda e conteúdo que exige sessão. |
| 3 | `faster-whisper` | Baixa o áudio e transcreve localmente quando não existe legenda. |

O Whisper só é usado quando habilitado. Ele pode levar vários minutos por vídeo,
principalmente em CPU, e baixa o modelo no primeiro uso.

## Vídeos que exigem login

Alguns vídeos ou playlists só ficam disponíveis em uma conta autenticada. Nesses
casos, exporte a sessão do YouTube no formato Netscape como `cookies.txt`, coloque
o arquivo na raiz do projeto e selecione **arquivo cookies.txt** na interface.

> **Segurança:** `cookies.txt` dá acesso à sua sessão. Nunca publique, envie ou
> versione esse arquivo. O `.gitignore` deste projeto bloqueia nomes comuns de
> arquivos de cookies.

No Windows, a leitura direta dos cookies do Chrome e Edge pode falhar devido ao
App-Bound Encryption. Um arquivo exportado ou o Firefox costuma ser a opção mais
confiável.

## Arquivos principais

| Arquivo | Finalidade |
|---|---|
| `app.py` | Servidor local e interface web. |
| `yt_transcript_md.py` | Extração, conversão para Markdown e CLI. |
| `transcricao_audio.py` | Fallback opcional com Whisper. |
| `diagnostico.py` | Diagnóstico de dependências e vídeos problemáticos. |
| `CHANGELOG.md` | Histórico e contexto das alterações. |

## Testes

```bash
python -m unittest discover -s tests -v
```

O workflow em `.github/workflows/checks.yml` verifica sintaxe e testes no GitHub
Actions com Python 3.10 e 3.12.

## Observações

- O app chama `python -m yt_dlp`, portanto não depende de um executável `yt-dlp`
  disponível no `PATH`.
- Gerar novamente a transcrição do mesmo vídeo na mesma pasta sobrescreve o
  arquivo anterior.
- Transcrições, cookies, ambientes virtuais e caches são ignorados pelo Git.

