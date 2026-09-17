# transcripts/

Saída da interface web ([app.py](../app.py)). Cada transcrição gerada pelo
navegador é gravada aqui automaticamente, sem você precisar clicar em "Baixar".

Vídeos avulsos ficam diretamente nesta pasta. Playlists recebem uma subpasta com
o título e o ID da lista, mantendo cada coleção separada.

## Nome dos arquivos

`{titulo-em-slug}-{video_id}.md` — por exemplo
`chegue-em-garotas-mas-do-jeito-certo-HyUE5Bg4ZuU.md`.

O `video_id` no fim é o que garante nome único: dois vídeos de título igual não
se sobrescrevem. O mesmo vídeo transcrito de novo **sobrescreve** o arquivo
anterior.

## O que tem dentro

Frontmatter YAML (`title`, `channel`, `url`, `video_id`, `language`, `duration`,
`words`, `source`, `extracted_at`) seguido do texto em parágrafos. O campo
`source` diz por qual caminho a transcrição veio: `youtube-transcript-api`,
`yt-dlp` ou `whisper:small` — útil para saber se o texto foi lido de uma legenda
oficial ou reconhecido do áudio (que erra mais).

## O que não fazer

- Não edite os `.md` aqui esperando manter a edição: gerar o mesmo vídeo de novo
  apaga suas mudanças. Copie para outra pasta antes de mexer.
- A CLI ([yt_transcript_md.py](../yt_transcript_md.py)) **não** escreve aqui — ela
  usa `-o ./transcricoes` por padrão.
