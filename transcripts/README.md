# transcripts/

Saída da interface web ([app.py](../app.py)). Cada transcrição gerada pelo
navegador é gravada aqui automaticamente, sem você precisar clicar em "Baixar".

```text
transcripts/
├── avulsos/                      vídeos colados como link direto
│   └── titulo-do-video-ID.md
└── titulo-da-playlist-PLxxxx/    uma pasta por playlist
    └── titulo-do-video-ID.md
```

- **`avulsos/`**: todo vídeo transcrito a partir de um link de vídeo comum. O nome
  da pasta é a constante `PASTA_AVULSOS` em [app.py](../app.py).
- **Playlists** (inclusive "Assistir mais tarde") recebem uma subpasta com o título
  e o ID da lista, mantendo cada coleção separada.

Arquivos gerados antes dessa organização podem estar soltos na raiz desta pasta.
Eles continuam valendo: a lista de playlists os reconhece como "já transcrito".
Mova-os para `avulsos/` se quiser tudo no mesmo lugar.

## Nome dos arquivos

`{titulo-em-slug}-{video_id}.md`, por exemplo
`chegue-em-garotas-mas-do-jeito-certo-HyUE5Bg4ZuU.md`.

O `video_id` no fim garante nome único: dois vídeos de título igual não se
sobrescrevem. O mesmo vídeo transcrito de novo **sobrescreve** o arquivo anterior
(na mesma pasta). O `video_id` também é como o app descobre o que já foi
transcrito, então **não renomeie o final do nome**.

## O que tem dentro

Frontmatter YAML (`title`, `channel`, `url`, `video_id`, `language`, `duration`,
`words`, `source`, `extracted_at`) seguido do texto em parágrafos. O campo
`source` diz por qual caminho a transcrição veio: `youtube-transcript-api`,
`yt-dlp` ou `whisper:small`, útil para saber se o texto foi lido de uma legenda
oficial ou reconhecido do áudio (que erra mais).

## O que não fazer

- Não edite os `.md` aqui esperando manter a edição: gerar o mesmo vídeo de novo
  apaga suas mudanças. Copie para outra pasta antes de mexer.
- A CLI ([yt_transcript_md.py](../yt_transcript_md.py)) **não** escreve aqui: ela
  usa `-o ./transcricoes` por padrão.
