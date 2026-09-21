# interface/

A página web do app, separada em três arquivos. O [app.py](../app.py) junta os três
num documento só a cada acesso (função `carregar_pagina`), então **editar e recarregar
o navegador basta**, sem reiniciar o servidor.

| Arquivo | O que tem |
|---|---|
| `pagina.html` | Estrutura da página e o conjunto de ícones SVG. Traz marcadores que o servidor preenche: `<!--ESTILO-->`, `<!--SCRIPT-->`, `<!--AVISO-->`, `<!--COOKIES_ARQUIVO-->` e `<!--WHISPER-->`. |
| `estilo.css` | Todo o visual. Cores só como tokens (`--bg`, `--surface`, `--accent`...), definidos uma vez para o tema claro (`:root`) e outra para o escuro (`.dark`). |
| `app.js` | Comportamento: tema, campo de links, login, lista de playlists, escolha de vídeos e fila de transcrição. Fala com o servidor pelas rotas `/api/...`. |

## Regras deste visual

- **Cor nova = token novo nos dois temas.** Nunca escreva `#hex` solto no CSS fora do
  bloco de tokens. Confira contraste (mínimo 4,5:1 para texto) nos dois temas antes de
  fixar um valor.
- **Sem cápsulas nem selos** (fundo colorido arredondado para status ou contagem).
  Status e contagem são texto, com cor e, quando ajuda, um ícone.
- **Tema:** um botão só, com troca em fade linear (`--duracao-tema`). O fade e o
  fallback usam o mesmo token de duração.
- **Sem `prefers-reduced-motion` desligando animações**: é uma escolha deliberada.
- Título de vídeo entra na tela com `textContent` ou `esc()`, nunca como HTML cru.
