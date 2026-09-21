# Changelog

Todas as mudanças relevantes deste projeto. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Datas em DD/MM/AAAA.

## [Não publicado]

### Alterado — mensagem clara para lista privada sem sessão válida (21/09/2026)

- **Sintoma:** a "Assistir mais tarde" falhava com `ERROR: [youtube:tab] WL: YouTube said:
  The playlist does not exist.`, texto que não diz o que fazer. Hoje cedo a mesma lista abriu
  com 280 vídeos; depois de uma nova exportação do `cookies.txt` passou a falhar.
- **Causa investigada:** o arquivo regravado tinha 12 cookies e não trazia `LOGIN_INFO`, `SID`,
  `HSID`, `SSID`, `SAPISID`, `__Secure-1PSID` nem `__Secure-1PAPISID`. Sem eles o YouTube trata
  a requisição como deslogada e responde que a lista privada "não existe". Causa provável: o
  YouTube rotaciona os cookies da janela que continua aberta. Só os NOMES foram inspecionados;
  nenhum valor foi lido.
- `_erro_ytdlp` reconhece "playlist does not exist" e "this playlist is private". Com cookies,
  manda exportar de novo (janela anônima, `robots.txt`, fechar a janela). Sem cookies, manda
  escolher "arquivo cookies.txt" em Opções.
- `DICA_COOKIES` e o README passaram a descrever esse jeito de exportar.

### Corrigido — cookies e mensagens de bloqueio enganosas (21/09/2026)

- **Sintoma:** um vídeo falhou com `IpBlocked` e, na linha do `yt-dlp`, a mensagem de que o
  Windows não deixa ler os cookies do Chrome/Edge/Brave. Ou seja, a tentativa foi feita com
  o seletor **Cookies** em um navegador, caminho que nunca funciona no Windows (o navegador
  criptografa o banco de cookies). O seletor estava dentro de **Opções**, fechado, e não dava
  para ver o que estava valendo.
- **`arquivo cookies.txt` agora vem selecionado** quando o arquivo existe na pasta
  (`html_opcao_cookies()`), e os seletores de cookies e pausa têm `autocomplete="off"`, para o
  navegador não restaurar um valor antigo ao recarregar a página.
- **Resumo ao lado de "Opções"** ("· cookies.txt · pausa 6 s"), atualizado a cada mudança. Se
  o cookie escolhido for chrome, edge, brave ou opera no Windows, o resumo fica em vermelho com
  "(não funciona no Windows)".
- **Dica de erro inteligente:** quando a falha é bloqueio de IP ou limite de requisições
  (`IpBlocked`, `RequestBlocked`, `429`, `Too Many Requests`), a dica manda esperar e reduzir a
  fila, e **não** sugere mais o Whisper (ele também baixa o áudio do YouTube, então seria
  bloqueado igual). A detecção usa `\b429\b` para não confundir com "1429".
- A mensagem de `IpBlocked` deixou de sugerir `--cookies-from-browser chrome` (não funciona no
  Windows) e passou a sugerir esperar ou usar `cookies.txt`. Vale também para a CLI.
- **Armadilha do meu próprio script de edição:** escrever `\b` em texto Python comum gera um
  caractere de backspace no arquivo, em vez de `\b` da expressão regular. Os testes de
  `foi_bloqueio` pegaram o caso `1429`. Em edição por script, usar string crua (`r"..."`).

### Alterado — novo visual, com tema claro e escuro (21/09/2026)

- **Interface refeita** para um visual mais limpo e fluido: campo de links em destaque
  com o botão principal dentro dele, idioma como controle segmentado, opções
  secundárias recolhidas em **Opções**, playlists como cartões com ícone e marca de
  seleção, e barra de progresso fina na borda do campo (indeterminada ao ler links,
  proporcional ao andar da fila).
- **Tema claro e escuro** com um botão só, no padrão de fade linear (View Transitions
  API; sem ela, `transition` em `html` e `body`). A escolha fica salva no navegador e o
  primeiro acesso segue o tema do sistema. Um script no `<head>` aplica o tema antes da
  primeira pintura, para a página não piscar no tema errado.
- **Contraste conferido por cálculo (WCAG), nos dois temas.** Um par falhou na primeira
  versão (botão principal no escuro, 4,47:1) e o tom do acento foi ajustado para 5,0:1.
  Contornos de caixa de marcar e de chave usam um token próprio (`--borda-forte`) porque
  contorno de controle exige 3:1, e o token de linha decorativa não chega nisso.
- **Sem cápsulas nem selos:** o selo "CC" foi removido; "já transcrito", contagens e
  status são texto, com cor e ícone.
- **Página tirada de dentro do `app.py`** para a pasta `interface/` (`pagina.html`,
  `estilo.css`, `app.js`), com README próprio. Eram 750 linhas de HTML/CSS/JS dentro de
  um texto do Python. O servidor monta o documento a cada acesso, então editar e
  recarregar o navegador basta. O `app.py` encolheu de ~1.300 para ~550 linhas.
- **Alinhamento:** as playlists ficavam 2 px para dentro do cartão "Assistir mais tarde"
  (efeito do `padding` da lista rolável). Corrigido com margem negativa compensando o
  padding, que continua existindo para a sombra do hover não ser cortada.

### Adicionado — pausa entre vídeos e "já transcrito" (21/09/2026)

- **Pausa entre vídeos da fila**, em **Opções** (nenhuma, 3, 6, 10 ou 20 s; padrão 6 s),
  com variação de ±30% para o ritmo não ser de robô. Reduz o risco de HTTP 429 / IpBlocked
  ao transcrever muitos vídeos seguidos. A tela mostra a contagem enquanto espera.
- **"Já transcrito"** na lista de vídeos de uma playlist: o servidor procura o ID do
  vídeo (últimos 11 caracteres do nome do arquivo) em **todas** as pastas de
  `transcripts/`, então um vídeo feito por outra playlist ou como link avulso também
  conta. **Marcar todos** pula esses; dá para marcá-los à mão para refazer.

### Alterado — vídeos avulsos vão para `transcripts/avulsos/` (21/09/2026)

- Antes, o vídeo colado como link direto era salvo solto na raiz de `transcripts/`, ao
  lado das pastas das playlists. Agora vai para a subpasta `avulsos/` (constante
  `PASTA_AVULSOS` no `app.py`). Arquivos antigos na raiz continuam valendo: o
  "já transcrito" os reconhece. A CLI não foi alterada.

### Adicionado — escolher os vídeos antes de transcrever (21/09/2026)

- **Sintoma que motivou:** a "Assistir mais tarde" tem 280 vídeos e o app transcrevia a
  playlist inteira sem perguntar.
- Depois de ler um link de playlist, o app mostra a **lista de vídeos com caixas de
  marcar**, começando tudo desmarcado. Botões **Marcar todos** e **Desmarcar todos**,
  contador ("12 de 280 selecionados") e botão "Transcrever selecionados (N)".
- **Campo de filtro por título.** "Marcar todos" age só sobre o que está visível, então
  dá para filtrar um assunto e marcar só esses. Com centenas de vídeos, ir marcando um a
  um seria inviável.
- **Vídeo avulso continua indo direto,** sem tela extra. Misturando links, os avulsos
  entram sempre e a tela avisa quantos são.
- **Cancelar** volta ao estado inicial sem transcrever nada.
- **Como foi feito:** `run()` do JavaScript foi dividido em etapas. `run()` lê os
  links, `mostrarSeletor()` cuida da escolha e `transcrever()` roda a fila. `montarJobs()`
  monta a fila a partir do que foi marcado. Títulos entram com `textContent`, nunca como
  HTML, para um título de vídeo com `<` não quebrar a página.
- Nenhuma rota nova: o servidor já devolvia a lista de vídeos em `/api/expand`.

### Corrigido — "Requested format is not available" ao buscar legenda (21/09/2026)

- **Sintoma:** vídeo com legenda automática falhava com `yt-dlp → ERROR: Requested format
  is not available`, e a `youtube-transcript-api` respondia `IpBlocked`.
- **Causa 1:** o YouTube protege os formatos com um desafio em JavaScript. O `yt-dlp` só
  usa o `deno` por padrão; nesta máquina há `node`, que precisa ser pedido com
  `--js-runtimes node`, e o pacote `yt-dlp-ejs` traz o script do desafio. Sem isso o
  `yt-dlp` só enxergava imagens, e o erro de formato abortava **antes** de gravar a
  legenda. Correção em `ytdlp_base_cmd()`, que é usada por legenda, playlist e Whisper.
  O Whisper precisava disso mais do que todos: ele baixa o áudio.
- **Causa 2 (rede de segurança):** `--ignore-no-formats-error` na busca de legenda. O app
  nunca baixa vídeo ali, então a falta de formato não pode impedir a gravação do texto.
- `yt-dlp-ejs` entrou em `requirements.txt`.
- **Fora do alcance do código:** o `HTTP 429 Too Many Requests` e o `IpBlocked` são o
  YouTube limitando o IP depois de muitas requisições seguidas (por exemplo, uma playlist
  inteira). Passa sozinho com o tempo.

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
