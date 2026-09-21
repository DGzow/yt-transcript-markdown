# Changelog

Todas as mudanças relevantes deste projeto. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Datas em DD/MM/AAAA.

## [Não publicado]

### Adicionado — cartão "Assistir mais tarde" (21/09/2026)

- Cartão fixo no bloco **Minha conta** que liga/desliga o link
  `youtube.com/playlist?list=WL` no campo de links e já seleciona **arquivo cookies.txt**
  no seletor de cookies. Se o `cookies.txt` não estiver na pasta, mostra um aviso.
- **Por que fixo e fora da lista da conta:** a YouTube Data API não entrega a "Assistir
  mais tarde" (o Google a esconde dos apps desde 2016), então ela nunca viria da lista
  do login. O caminho que funciona é o `yt-dlp` com `cookies.txt`, e esse não depende do
  login Google, por isso o cartão aparece mesmo desconectado.
- A função de clique foi generalizada (`alternarLink`) e atende os dois grupos de cartões.

### Adicionado — login com Google e lista das minhas playlists (21/09/2026)

- **`youtube_conta.py`**: login OAuth com a conta Google e listagem das playlists pela
  YouTube Data API v3. A interface ganhou o bloco **Minha conta**: botão "Entrar com
  Google", lista de playlists clicáveis (cada clique liga/desliga o link da playlist no
  campo de links, então dá para marcar várias) e botão "Sair".
- **Por que OAuth e não o `cookies.txt`:** o `cookies.txt` entrega a sessão inteira do
  YouTube e o formato da página que lista playlists muda sem aviso. O OAuth pede uma
  permissão única e revogável, e a API oficial tem contrato estável.
- **Escopo `youtube.readonly` (somente leitura):** o app não consegue alterar nem apagar
  nada na conta.
- **Arquivos sensíveis:** `client_secret.json` (identifica o app, baixado do Google
  Cloud) e `token.json` (identifica o usuário, criado no login) entraram no `.gitignore`.
- **Limites conhecidos:** a "Assistir mais tarde" e as "Curtidas" não aparecem, porque a
  API não as expõe como playlists comuns. Com o app do Google Cloud em modo **Teste**, o
  login expira a cada 7 dias; o app detecta, apaga o token vencido e volta ao estado
  "desconectado" em vez de quebrar.
- **Bibliotecas importadas dentro das funções:** sem `google-auth-oauthlib` e
  `google-api-python-client` o app continua abrindo; só o bloco Minha conta avisa.
- Dependências novas em `requirements.txt`: `google-auth-oauthlib`,
  `google-api-python-client`. Testes novos em `tests/test_youtube_conta.py`.
- Rotas novas no servidor local: `GET /api/conta`, `GET /api/playlists`,
  `POST /api/conta/entrar`, `POST /api/conta/sair`.

### Adicionado — playlists na interface

- Links de playlist agora são expandidos automaticamente com o `yt-dlp` e todos os
  vídeos entram na fila de transcrição.
- Cada playlist ganha uma subpasta própria dentro de `transcripts/`. O nome inclui o
  título e o ID da playlist para evitar colisões; links de vídeos avulsos mantêm o
  comportamento anterior.
- A interface mostra o total real de vídeos, elimina entradas repetidas e indica a
  subpasta em que cada Markdown foi salvo.

### Adicionado — transcrição do áudio com Whisper (terceiro caminho)

- **`transcricao_audio.py`**: quando nem a `youtube-transcript-api` nem o yt-dlp acham
  legenda, baixa a trilha de áudio e transcreve **localmente** com `faster-whisper`.
  Nada sai da máquina. Na interface é o interruptor "Transcrever o áudio se não houver
  legenda" + seletor de modelo; na CLI, `--whisper [MODELO]` (padrão `small`).
- **O ffmpeg do sistema não é necessário.** O áudio é baixado no formato original
  (`-f bestaudio[ext=m4a]/bestaudio/best`, sem pós-processamento) e o PyAV — que vem
  junto com o `faster-whisper` — decodifica direto. Exigir ffmpeg significaria mais uma
  instalação manual no Windows.
- **`condition_on_previous_text=False`** na chamada do Whisper: em áudio longo, o padrão
  (`True`) entra em loop repetindo a mesma frase. `vad_filter=True` corta o silêncio,
  o que reduz alucinação e tempo de CPU.
- **Modelo em cache de módulo** (`_cache_modelo`), com chave `(nome, device, compute_type)`:
  carregar o modelo custa segundos, e uma fila de vídeos recarregaria a cada item.
- **CPU com `int8`, GPU com `float16`**, decidido em tempo de execução por
  `ctranslate2.get_cuda_device_count()`.
- **O campo `source` do frontmatter passa a registrar `whisper:small`** (e o modelo usado),
  para dar para distinguir texto lido de legenda oficial de texto reconhecido do áudio.

### Corrigido

- A expansão de playlist chamava o tradutor de erros do `yt-dlp` sem o argumento
  que informa se havia cookies, causando `_erro_ytdlp() missing 1 required positional
  argument` em vez de mostrar a causa real.
- Quando a leitura de cookies do Chrome, Edge ou Brave falha, playlists públicas
  agora são tentadas novamente sem cookies automaticamente.

- **Aviso falso "Falta instalar: yt-dlp" com o yt-dlp instalado.** `checar_dependencias()`
  procurava o executável (`shutil.which("yt-dlp")`), e o `pip install yt-dlp` nem sempre
  deixa um `yt-dlp.exe` no PATH — nesta máquina, `C:\Python314\Scripts` só tem o `pip`.
  Agora a checagem é pelo **módulo** (`importlib.util.find_spec("yt_dlp")`).
- **O fallback de yt-dlp nunca rodava, pelo mesmo motivo.** `fetch_via_ytdlp()` chamava
  `subprocess.run(["yt-dlp", ...])`, que falhava sem o `.exe`. Passou a montar o comando
  com `[sys.executable, "-m", "yt_dlp", ...]`, caindo no `.exe` só se o módulo não existir.
  Consequência prática: com uma das duas bibliotecas falhando, o app dizia "não consegui
  baixar a legenda" sem nunca ter tentado o segundo caminho.
- **`diagnostico.py` carregava o mesmo erro** — reportava "yt-dlp NÃO instalado" e chamava
  `["yt-dlp", "--list-subs"]`. Passou a usar `core.ytdlp_disponivel()` / `core.ytdlp_base_cmd()`,
  e agora também informa se o `faster-whisper` está disponível.
- **Saída do yt-dlp lida como cp1252 no Windows**, o que estourava `UnicodeDecodeError`
  em mensagem de erro com acento. `subprocess.run` agora recebe `encoding="utf-8",
  errors="replace"`.

### Adicionado

- **Suporte a `cookies.txt` (formato Netscape)**, via `--cookies ARQUIVO` na CLI e a opção
  "arquivo cookies.txt" no seletor COOKIES da interface web (o app procura `cookies.txt`,
  `www.youtube.com_cookies.txt` ou `youtube.com_cookies.txt` na própria pasta).
  **Motivo:** a partir do Chrome 127 o banco de cookies usa *app-bound encryption*, e o
  `--cookies-from-browser chrome|edge` morre com `Failed to decrypt with DPAPI` no Windows.
  O caminho do navegador continua no seletor, mas deixou de ser o recomendado.
- **Nova tentativa com `--sub-langs all`** quando o yt-dlp responde "no subtitles for the
  requested languages". Existindo legenda em outro idioma, entregar em espanhol vale mais
  que não entregar nada.
- **`_erro_ytdlp()`**: traduz a saída crua do yt-dlp para uma linha que diz o que fazer
  (DPAPI, restrição de idade, "sign in to confirm", DRM, vídeo sem legenda nenhuma).
  Antes, o card de erro mostrava um `stderr` truncado em 260 caracteres.

### Documentação

- Criados `README.md` na raiz e em `transcripts/`, e este `CHANGELOG.md`.

### Observado (não é bug do app)

- Vídeos sem **nenhuma** faixa de legenda exposta ao público retornam
  `TranscriptsDisabled` na `youtube-transcript-api` e "has no subtitles" no yt-dlp.
  Verificado no caso `HyUE5Bg4ZuU`: a página `/watch` anônima não traz `captionTracks`,
  e nenhum player client (`web`, `mweb`, `ios`, `web_safari`, `android_vr`) lista legenda —
  o `tv` ainda responde "DRM protected". Nesse cenário só há dois caminhos: cookies de uma
  sessão logada que enxergue a transcrição, ou transcrever o áudio localmente — que é
  exatamente o que o `--whisper` passou a fazer.
- **Python 3.14 tem rodas para tudo o que o Whisper precisa** (`ctranslate2` 4.8.1,
  `av` 18.0.0, `onnxruntime` 1.28.0), verificado com `pip install --dry-run`. Nenhuma
  compilação local foi necessária.
</content>
