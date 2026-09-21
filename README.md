# YouTube Transcript to Markdown

Aplicativo local para transformar vídeos e playlists do YouTube em arquivos
Markdown. Cada vídeo gera um `.md` com metadados, texto organizado em parágrafos
e marcações de tempo clicáveis.

## Recursos

- Vídeos individuais ou playlists completas pela interface web.
- Uma subpasta própria em `transcripts/` para cada playlist.
- Legendas públicas via `youtube-transcript-api` e `yt-dlp`.
- Transcrição de áudio sem legenda com Whisper, opcional e executado localmente.
- Preferência de idioma, timestamps, cookies de sessão e processamento em fila com pausa.
- Tema claro e escuro (botão no canto superior direito).
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
4. Se o link for de **playlist**, o app lista os vídeos antes de transcrever. Marque os
   que quiser (ou **Marcar todos**), use o campo de filtro para achar por título e clique
   em **Transcrever selecionados**. Vídeo avulso é transcrito direto.

Vídeos colados como link direto vão para `transcripts/avulsos/`. Cada playlist ganha
uma pasta própria:

```text
transcripts/
├── avulsos/
│   └── titulo-do-video-ID.md
└── titulo-da-playlist-PLxxxx/
    ├── primeiro-video-ID.md
    └── segundo-video-ID.md
```

Ao ler uma playlist, o app marca como "já transcrito" os vídeos que já têm arquivo em
qualquer pasta de `transcripts/`, e o botão **Marcar todos** pula esses. Por isso, não
renomeie o final do nome dos arquivos (o ID do vídeo).

Entre um vídeo e outro da fila há uma **pausa** (padrão de 6 s, ajustável em
**Opções**) para o YouTube não bloquear o seu IP em filas grandes.

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

## Minhas playlists (login com Google)

O bloco **Minha conta** da interface lista as playlists da sua conta do YouTube. Clique
em uma (ou em várias) para adicionar o link ao campo de links e depois em **Gerar
Markdown**. A permissão é somente leitura.

Configuração única, no Google Cloud:

1. Crie um projeto em [console.cloud.google.com](https://console.cloud.google.com).
2. Em **APIs e serviços → Biblioteca**, ative a **YouTube Data API v3**.
3. Em **Tela de permissão OAuth**, escolha público **Externo**, adicione o seu e-mail
   como usuário de teste e o escopo `.../auth/youtube.readonly`.
4. Em **Credenciais**, crie um **ID do cliente OAuth** do tipo **App para computador**,
   baixe o JSON e salve na raiz do projeto como `client_secret.json`.

Depois, clique em **Entrar com Google** na interface. O login fica salvo em `token.json`;
**Sair** apaga esse arquivo.

> **Segurança:** `client_secret.json` e `token.json` são ignorados pelo Git. Não os
> publique nem os envie a ninguém.

Com o app do Google Cloud em modo **Teste**, o login vale por 7 dias e depois pede nova
entrada. Publicar o app (aparece um aviso de "app não verificado", normal para uso
pessoal) remove esse prazo. "Assistir mais tarde" e "Curtidas" não aparecem na lista, por
limitação da API. Para a "Assistir mais tarde" existe um cartão fixo no mesmo bloco: ele
preenche o link e escolhe o `cookies.txt` por você (o arquivo precisa estar na pasta do
app, veja "Vídeos que exigem login" abaixo).

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
| `app.py` | Servidor local (rotas e transcrição). |
| `interface/` | Página web: HTML, CSS e JavaScript em arquivos separados. |
| `yt_transcript_md.py` | Extração, conversão para Markdown e CLI. |
| `youtube_conta.py` | Login com Google e listagem das playlists da conta. |
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

