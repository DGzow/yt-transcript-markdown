// ============================================================================
// Comportamento da página. Fala com o servidor local (app.py) por fetch().
// Ordem do arquivo: utilitários, tema, campo de links, conta, resultados,
// fluxo principal (ler links -> escolher vídeos -> transcrever).
// ============================================================================

const $ = (id) => document.getElementById(id);
const box = $('urls'), results = $('results'), statusEl = $('status');
let lang = 'pt', done = [];

// ---- utilitários -----------------------------------------------------------

// Escapa texto antes de virar HTML (título de vídeo com "<" não pode quebrar a página).
const esc = (s) => s.replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));

// Ícone do conjunto SVG definido no topo do HTML.
const ic = (nome, extra = '') =>
  '<svg class="ic ' + extra + '" aria-hidden="true"><use href="#i-' + nome + '"/></svg>';

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200);
}

const esperar = (ms) => new Promise(r => setTimeout(r, ms));

// ---- tema claro/escuro -----------------------------------------------------
// A troca usa a View Transitions API: o navegador tira uma "foto" da página, a
// classe muda, e o CSS faz a foto nova aparecer por cima em fade linear.
// Sem a API, a classe `tema-fallback` faz html e body trocarem de cor com transition.

const raiz = document.documentElement;

function aplicarTema(escuro) {
  raiz.classList.toggle('dark', escuro);
  $('tema').setAttribute('aria-label', escuro ? 'Mudar para tema claro' : 'Mudar para tema escuro');
}

$('tema').addEventListener('click', () => {
  const escuro = !raiz.classList.contains('dark');
  try { localStorage.setItem('tema', escuro ? 'escuro' : 'claro'); } catch (_) {}
  if (document.startViewTransition) document.startViewTransition(() => aplicarTema(escuro));
  else aplicarTema(escuro);
});

if (!document.startViewTransition) raiz.classList.add('tema-fallback');
aplicarTema(raiz.classList.contains('dark'));

// ---- campo de links e opções -----------------------------------------------

// textarea que cresce conforme você cola
const grow = () => { box.style.height = 'auto'; box.style.height = box.scrollHeight + 'px'; };

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

// Barra de progresso sob o campo: 'off' (invisível), 'indet' (trabalhando, sem total
// conhecido) ou 'det' (fração p, de 0 a 1).
const barra = $('progresso');
function progresso(estado, p) {
  barra.classList.toggle('on', estado !== 'off');
  barra.classList.toggle('indet', estado === 'indet');
  if (p != null) barra.style.setProperty('--p', (p * 100) + '%');
}

// Trava o botão principal enquanto há trabalho em andamento.
function ocupado(on) {
  $('go').disabled = on;
  if (!on) progresso('off');
}

// ---- conta do YouTube ------------------------------------------------------

const contaMsg = $('conta-msg'), btnEntrar = $('conta-entrar'), btnSair = $('conta-sair');

// Pede ao servidor o estado do login e ajusta botões e mensagem conforme a resposta.
async function contaAtualizar() {
  $('playlists').innerHTML = '';
  btnEntrar.hidden = btnSair.hidden = true;
  let s;
  try { s = await (await fetch('/api/conta')).json(); }
  catch { contaMsg.textContent = 'o servidor local não respondeu'; return; }

  if (s.estado === 'sem_bibliotecas') {
    contaMsg.textContent = 'faltam as bibliotecas do Google. Rode: pip install google-auth-oauthlib google-api-python-client';
  } else if (s.estado === 'sem_client_secret') {
    contaMsg.textContent = 'coloque o client_secret.json na pasta do app para poder entrar (veja o README)';
  } else if (s.estado === 'desconectado') {
    contaMsg.textContent = 'Entre com o Google para ver e escolher as suas playlists.';
    btnEntrar.hidden = false;
  } else {
    contaMsg.innerHTML = '<span class="ponto"></span>Conectado. Clique nas playlists para adicioná-las ao campo de links.';
    btnSair.hidden = false;
    playlistsCarregar();
  }
}

async function playlistsCarregar() {
  const lista = $('playlists');
  contaMsg.innerHTML = '<span class="ponto"></span>Conectado. Carregando playlists...';
  let r;
  try { r = await (await fetch('/api/playlists')).json(); }
  catch { contaMsg.textContent = 'o servidor local não respondeu'; return; }
  if (!r.ok) { contaMsg.textContent = r.error; contaAtualizar(); return; }

  contaMsg.innerHTML = '<span class="ponto"></span>Conectado. Clique nas playlists para adicioná-las ao campo de links.';
  lista.innerHTML = '';
  if (!r.playlists.length) { contaMsg.textContent = 'Nenhuma playlist encontrada nesta conta.'; return; }
  for (const p of r.playlists) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'cartao';
    b.dataset.url = p.url;
    b.setAttribute('aria-pressed', 'false');
    b.innerHTML = '<span class="ic-caixa">' + ic('lista') + '</span>' +
      '<span class="titulo">' + esc(p.titulo) + '</span>' +
      '<span class="info">' + p.videos + (p.videos === 1 ? ' vídeo' : ' vídeos') + '</span>' +
      ic('check', 'marca');
    lista.appendChild(b);
  }
  sincronizarCartoes();
}

// Deixa cada cartão "ligado" só se o link dele está no campo de texto.
function sincronizarCartoes() {
  const linhas = box.value.split('\n').map(s => s.trim()).filter(Boolean);
  document.querySelectorAll('.cartao').forEach(c =>
    c.setAttribute('aria-pressed', String(linhas.includes(c.dataset.url))));
}
box.addEventListener('input', () => { grow(); sincronizarCartoes(); });

// Clicar num cartão liga/desliga o link dele no campo de texto (um link por linha).
// Serve tanto para as playlists da conta quanto para os cartões fixos (#fixas).
function alternarLink(e) {
  const b = e.target.closest('.cartao'); if (!b) return;
  const linhas = box.value.split('\n').map(s => s.trim()).filter(Boolean);
  const ligada = linhas.includes(b.dataset.url);
  const novas = ligada ? linhas.filter(l => l !== b.dataset.url) : [...linhas, b.dataset.url];
  box.value = novas.join('\n');
  grow(); sincronizarCartoes();

  // Cartão que depende do cookies.txt: já deixa o seletor de cookies pronto.
  if (b.dataset.cookies && !ligada) {
    const opcao = [...$('cookies').options].find(o => o.value === 'arquivo');
    if (opcao && !opcao.disabled) $('cookies').value = 'arquivo';
    else toast('Falta o cookies.txt na pasta do app (veja o README)');
  }
}
$('playlists').addEventListener('click', alternarLink);
$('fixas').addEventListener('click', alternarLink);

btnEntrar.addEventListener('click', async () => {
  btnEntrar.disabled = true;
  contaMsg.textContent = 'Aguardando você aprovar na aba que abriu no navegador...';
  let r;
  try { r = await (await fetch('/api/conta/entrar', {method: 'POST'})).json(); }
  catch { r = {ok: false, error: 'o servidor local não respondeu'}; }
  btnEntrar.disabled = false;
  if (r.ok) contaAtualizar();
  else contaMsg.textContent = r.error;   // mantém o botão visível para tentar de novo
});

btnSair.addEventListener('click', async () => {
  await fetch('/api/conta/sair', {method: 'POST'});
  toast('Você saiu da conta');
  contaAtualizar();
});

// ---- resultados ------------------------------------------------------------

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
      '<button class="btn ghost" data-act="open">Abrir no YouTube</button>' +
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

// ---- fluxo principal -------------------------------------------------------

// Etapa 1: ler cada link. Playlist vira uma lista de vídeos; vídeo avulso passa direto.
async function run() {
  const inputs = box.value.split('\n').map(s => s.trim()).filter(Boolean);
  if (!inputs.length) { box.focus(); toast('Cole um link primeiro'); return; }

  ocupado(true); progresso('indet');
  $('empty').style.display = 'none';
  $('seletor').hidden = true; $('seletor').innerHTML = '';
  results.innerHTML = ''; done = []; renderBulk();

  const grupos = [];
  for (let i = 0; i < inputs.length; i++) {
    statusEl.innerHTML = 'lendo link <b>' + (i + 1) + '/' + inputs.length + '</b>: ' +
      esc(inputs[i].slice(0, 60));
    try {
      const res = await fetch('/api/expand', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: inputs[i], cookies: $('cookies').value})
      });
      const expanded = await res.json();
      if (!expanded.ok) { renderCard(expanded); continue; }
      grupos.push(expanded);
    } catch (err) {
      renderCard({ok: false, error: 'O servidor local não respondeu ao ler a playlist.'});
    }
  }

  ocupado(false);
  if (!grupos.some(g => g.videos.length)) {
    statusEl.textContent = 'nenhum vídeo encontrado';
    if (!results.children.length) $('empty').style.display = '';
    return;
  }

  // Só vídeos avulsos: segue direto. Havendo playlist, para aqui para você escolher.
  if (!grupos.some(g => g.is_playlist)) return transcrever(montarJobs(grupos));
  mostrarSeletor(grupos);
}

// Transforma os grupos em fila de trabalho. `marcados` é o conjunto de vídeos escolhidos
// nas playlists (chave "índice do grupo|id do vídeo"); vídeo avulso entra sempre.
function montarJobs(grupos, marcados) {
  const jobs = [], seen = new Set();
  grupos.forEach((g, gi) => g.videos.forEach(v => {
    if (g.is_playlist && marcados && !marcados.has(gi + '|' + v.video_id)) return;
    const key = v.video_id + '|' + (g.folder || '');
    if (seen.has(key)) return;   // mesmo vídeo repetido na mesma pasta
    seen.add(key);
    jobs.push({url: v.url, video_id: v.video_id, title: v.title,
      folder: g.folder, playlist_title: g.title});
  }));
  return jobs;
}

// Etapa 2: lista os vídeos de cada playlist com caixas de marcar.
function mostrarSeletor(grupos) {
  const painel = $('seletor');
  painel.innerHTML = ''; painel.hidden = false;
  statusEl.innerHTML = 'Escolha quais vídeos transcrever.';
  const avulsos = grupos.filter(g => !g.is_playlist).reduce((n, g) => n + g.videos.length, 0);
  const totalFeitos = grupos.filter(g => g.is_playlist)
    .reduce((n, g) => n + g.videos.filter(v => v.ja_transcrito).length, 0);

  const topo = document.createElement('div');
  topo.className = 'sel-barra';
  topo.innerHTML =
    '<div class="sel-busca-wrap">' + ic('busca') +
      '<input type="search" class="sel-busca" placeholder="Filtrar por título..." aria-label="Filtrar vídeos"></div>' +
    '<button type="button" class="btn" data-a="todos">Marcar todos</button>' +
    '<button type="button" class="btn ghost" data-a="nenhum">Desmarcar</button>' +
    '<span class="sel-cont" id="sel-cont"></span>';
  painel.appendChild(topo);

  grupos.forEach((g, gi) => {
    if (!g.is_playlist) return;
    const sec = document.createElement('section');
    sec.className = 'sel-grupo';
    const h = document.createElement('h3');
    h.textContent = (g.title || 'Playlist') + ' · ' + g.videos.length + (g.videos.length === 1 ? ' vídeo' : ' vídeos');
    const lista = document.createElement('div');
    lista.className = 'sel-lista';
    g.videos.forEach(v => {
      const lab = document.createElement('label');
      lab.className = 'sel-item' + (v.ja_transcrito ? ' feito' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.className = 'caixa'; cb.dataset.k = gi + '|' + v.video_id;
      if (v.ja_transcrito) cb.dataset.feito = '1';
      const tx = document.createElement('span');
      tx.className = 'txt';
      tx.textContent = v.title || v.video_id;   // textContent: título nunca vira HTML
      lab.append(cb, tx);
      if (v.ja_transcrito) {
        const f = document.createElement('span');
        f.className = 'feito-info';
        f.innerHTML = ic('check') + 'já transcrito';
        lab.append(f);
      }
      lista.appendChild(lab);
    });
    sec.append(h, lista);
    painel.appendChild(sec);
  });

  const rodape = document.createElement('div');
  rodape.className = 'sel-rodape';
  const notas = [];
  if (totalFeitos) notas.push('"Marcar todos" pula os ' + totalFeitos + ' já transcritos.');
  if (avulsos) notas.push('+ ' + avulsos + (avulsos === 1 ? ' vídeo avulso' : ' vídeos avulsos') + ' será transcrito também.');
  rodape.innerHTML =
    (notas.length ? '<span class="sel-nota">' + esc(notas.join(' ')) + '</span>' : '') +
    '<div class="direita">' +
      '<button type="button" class="btn ghost" id="sel-cancelar">Cancelar</button>' +
      '<button type="button" class="btn primary" id="sel-go">Transcrever selecionados</button>' +
    '</div>';
  painel.appendChild(rodape);

  const caixas = () => [...painel.querySelectorAll('input[data-k]')];
  const visiveis = () => caixas().filter(cb => !cb.parentElement.hidden);
  const marcadas = () => caixas().filter(cb => cb.checked);

  // Contador e botão de confirmar acompanham as caixas.
  function atualizar() {
    const n = marcadas().length;
    $('sel-cont').textContent = n + ' de ' + caixas().length + ' selecionados';
    $('sel-go').textContent = 'Transcrever selecionados (' + (n + avulsos) + ')';
    $('sel-go').disabled = (n + avulsos) === 0;
  }

  painel.addEventListener('change', atualizar);

  // "Marcar todos" vale para o que está VISÍVEL (filtre um termo e marque só esses)
  // e pula o que já foi transcrito. "Desmarcar" limpa tudo o que está visível.
  topo.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.a === 'todos') visiveis().forEach(cb => { if (!cb.dataset.feito) cb.checked = true; });
    else visiveis().forEach(cb => { cb.checked = false; });
    atualizar();
  });

  topo.querySelector('.sel-busca').addEventListener('input', (e) => {
    const termo = e.target.value.trim().toLowerCase();
    caixas().forEach(cb => {
      cb.parentElement.hidden = termo &&
        !cb.parentElement.querySelector('.txt').textContent.toLowerCase().includes(termo);
    });
  });

  $('sel-cancelar').onclick = () => {
    painel.hidden = true; painel.innerHTML = ''; statusEl.textContent = '';
    if (!results.children.length) $('empty').style.display = '';
  };
  $('sel-go').onclick = () => {
    const escolhidos = new Set(marcadas().map(cb => cb.dataset.k));
    painel.hidden = true; painel.innerHTML = '';
    transcrever(montarJobs(grupos, escolhidos));
  };

  atualizar();
}

// Etapa 3: transcreve a fila, um vídeo por vez, com pausa entre eles.
async function transcrever(jobs) {
  ocupado(true); progresso('det', 0);
  const wh = $('wh') && $('wh').checked ? $('whmodel').value : null;
  const pausa = Number($('pausa').value) * 1000;   // 0 = sem pausa

  for (let i = 0; i < jobs.length; i++) {
    statusEl.innerHTML = 'buscando legenda <b>' + (i + 1) + '/' + jobs.length + '</b>: ' +
      esc((jobs[i].title || jobs[i].url).slice(0, 60)) +
      (wh ? '<br>sem legenda, o Whisper assume. Acompanhe o andamento no terminal' : '');
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
    progresso('det', (i + 1) / jobs.length);

    // Pausa (com variação de ±30%, para o ritmo não ser de robô) antes do próximo vídeo.
    // Ajuda a não levar HTTP 429 / IpBlocked do YouTube em filas grandes.
    if (pausa && i < jobs.length - 1) {
      const ms = pausa * (0.7 + Math.random() * 0.6);
      statusEl.innerHTML = 'pausa de <b>' + Math.round(ms / 1000) + ' s</b> antes do próximo (evita bloqueio do YouTube)';
      await esperar(ms);
    }
  }

  statusEl.innerHTML = done.length
    ? '<b>' + done.length + '</b> de <b>' + jobs.length + '</b> pronto' + (done.length > 1 ? 's' : '') + '. Salvos em transcripts/'
    : 'nenhuma legenda encontrada';
  if (!results.children.length) $('empty').style.display = '';
  // deixa a barra cheia por um instante antes de sumir
  setTimeout(() => { if (!$('go').disabled) progresso('off'); }, 800);
  $('go').disabled = false;
}

// ---- início ----------------------------------------------------------------
contaAtualizar();
