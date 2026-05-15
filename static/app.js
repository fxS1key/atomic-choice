'use strict';

/* ── Atomic Choice — SPA frontend
 *
 *   Аутентификация: ник + пароль → /api/auth/login или /register.
 *   После входа в localStorage кладётся только { nick, wallet, approved } —
 *   приватный ключ остаётся на сервере. Бэкенд использует HTTP-only куку.
 *
 *   Админ-токен хранится в sessionStorage, отправляется заголовком
 *   X-Admin-Token. Чтобы попасть в админку, нужно нажать «Админ» и ввести
 *   токен из admin_token.txt.
 */

/* ── State ────────────────────────────────────────────────────────────────── */
let page          = 'home';
let pollAddr      = null;
let selOpt        = null;
let me            = null;      // { nick, wallet, approved, whitelisted }
let filter        = 'all';
let adminToken    = sessionStorage.getItem('ac_admin_token') || '';
let authMode      = 'login';   // login | register

/* ── Utils ────────────────────────────────────────────────────────────────── */
const $   = id => document.getElementById(id);
const ROOT = () => $('root');

async function api(method, path, body, headers = {}) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    credentials: 'same-origin',
  };
  if (body) opts.body = JSON.stringify(body);
  try {
    const r = await fetch(path, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok && !data.error) data.error = data.detail || `HTTP ${r.status}`;
    data._ok = r.ok;
    return data;
  } catch (e) {
    return { error: e.message, _ok: false };
  }
}

const adminApi = (m, p, b) =>
  api(m, p, b, adminToken ? { 'X-Admin-Token': adminToken } : {});

function toast(msg, type = 'info') {
  const d = document.createElement('div');
  d.className = 'toast ' + type;
  d.textContent = msg;
  $('toasts').appendChild(d);
  setTimeout(() => d.style.opacity = '0', 2800);
  setTimeout(() => d.remove(), 3100);
}

function fmtTime(unix) {
  return new Date(unix * 1000).toLocaleString('ru', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}
function timeLeft(unix) {
  const s = unix - Date.now() / 1000;
  if (s <= 0) return '';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h > 48) return Math.floor(h / 24) + ' дн.';
  if (h > 0)  return `${h}ч ${m}м`;
  if (m > 0)  return m + ' мин';
  return Math.floor(s) + ' сек';
}
function badge(status) {
  const map = {
    active:   ['b-active', '● ACTIVE'],
    ended:    ['b-ended',  '■ ENDED'],
    upcoming: ['b-upcoming', '◆ SOON'],
  };
  const [cls, lbl] = map[status] || ['b-ended', '—'];
  return `<span class="badge ${cls}">${lbl}</span>`;
}
const LABELS = ['А','Б','В','Г','Д','Е','Ж','З','И','К','Л','М','Н','О','П','Р'];
const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ── Router ───────────────────────────────────────────────────────────────── */
function nav(p, addr) {
  page = p;
  pollAddr = addr || null;
  selOpt = null;
  ['home', 'polls', 'create', 'admin'].forEach(x =>
    $('n-' + x)?.classList.toggle('on', x === p || (p === 'poll' && x === 'polls'))
  );
  render();
  window.scrollTo(0, 0);
}

/* ── Auth modal ───────────────────────────────────────────────────────────── */
function onWalletClick() {
  if (me) {
    if (!confirm(`Выйти из аккаунта ${me.nick}?`)) return;
    api('POST', '/api/auth/logout').then(() => {
      me = null;
      updateWalletUI();
      toast('Выход выполнен');
      render();
    });
    return;
  }
  openAuthModal('login');
}
function openAuthModal(mode = 'login') {
  setAuthMode(mode);
  $('auth-modal').style.display = 'flex';
  setTimeout(() => $('auth-nick').focus(), 50);
}
function closeAuthModal() {
  $('auth-modal').style.display = 'none';
  $('auth-error').classList.remove('show');
  $('auth-error').textContent = '';
}
function setAuthMode(mode) {
  authMode = mode;
  $('auth-tab-login')   .classList.toggle('on', mode === 'login');
  $('auth-tab-register').classList.toggle('on', mode === 'register');
  $('auth-submit').textContent = mode === 'login' ? 'Войти' : 'Зарегистрироваться';
  $('auth-title').textContent  = mode === 'login' ? '🔐 Вход' : '🆕 Регистрация';
  $('auth-pass').setAttribute('autocomplete', mode === 'login' ? 'current-password' : 'new-password');
}
async function doAuth() {
  const nick = $('auth-nick').value.trim();
  const pass = $('auth-pass').value;
  const err  = $('auth-error');
  err.classList.remove('show'); err.textContent = '';

  $('auth-submit').disabled = true;
  $('auth-submit').textContent = '⏳ ...';
  const res = await api('POST', `/api/auth/${authMode}`, { nick, password: pass });
  $('auth-submit').disabled = false;
  $('auth-submit').textContent = authMode === 'login' ? 'Войти' : 'Зарегистрироваться';

  if (!res._ok) {
    err.textContent = res.detail || res.error || 'Ошибка';
    err.classList.add('show');
    return;
  }
  me = res.user;
  updateWalletUI();
  closeAuthModal();
  toast(authMode === 'register'
    ? `✓ Зарегистрировано. Дождитесь подтверждения от организатора.`
    : `✓ Добро пожаловать, ${me.nick}`, 'ok');
  render();
}

function updateWalletUI() {
  const dot = $('wdot'), lbl = $('wallet-label'), btn = $('wallet-btn');
  if (me) {
    dot.className = 'wdot on';
    lbl.textContent = me.nick + (me.approved ? '' : ' ⏳');
    btn.classList.add('active');
  } else {
    dot.className = 'wdot off';
    lbl.textContent = 'Войти';
    btn.classList.remove('active');
  }
}

/* ── Admin token modal ────────────────────────────────────────────────────── */
function openTokenModal() {
  $('token-modal').style.display = 'flex';
  setTimeout(() => $('token-input').focus(), 50);
}
function closeTokenModal() {
  $('token-modal').style.display = 'none';
}
function submitToken() {
  const t = $('token-input').value.trim();
  if (!t) return;
  adminToken = t;
  sessionStorage.setItem('ac_admin_token', t);
  closeTokenModal();
  toast('🔑 Админ-токен сохранён', 'ok');
  if (page === 'admin') render();
}

/* ── Status ───────────────────────────────────────────────────────────────── */
async function checkStatus() {
  const tag = $('chain-tag');
  const r = await fetch('/api/admin/status', {
    headers: adminToken ? { 'X-Admin-Token': adminToken } : {},
  });
  if (r.status === 401) {
    // Можем хотя бы проверить соединение через публичный эндпоинт
    const pollsRes = await fetch('/api/polls').catch(() => null);
    const connected = pollsRes && pollsRes.ok;
    tag.textContent = connected ? 'Hardhat ✓' : 'No node';
    tag.classList.toggle('ok', !!connected);
    return null;
  }
  const s = await r.json().catch(() => null);
  if (!s) return null;
  tag.textContent = s.node_connected ? 'Hardhat ✓' : 'No node';
  tag.classList.toggle('ok', !!s.node_connected);
  return s;
}

/* ── Render dispatcher ────────────────────────────────────────────────────── */
async function render() {
  if (page === 'home')   return renderHome();
  if (page === 'polls')  return renderPolls();
  if (page === 'poll')   return renderPoll();
  if (page === 'create') return renderCreate();
  if (page === 'admin')  return renderAdmin();
}

/* ── HOME ─────────────────────────────────────────────────────────────────── */
async function renderHome() {
  const pd = await api('GET', '/api/polls');
  const polls  = pd.polls || [];
  const active = polls.filter(p => p.status === 'active');
  const status = await checkStatus();
  const connected = status?.node_connected ?? (polls.length > 0);

  ROOT().innerHTML = `<div class="page">
    <div class="stats">
      <div class="sc">
        <div class="sc-label">Node</div>
        <div class="sc-val" style="font-size:1.1rem;color:${connected?'var(--green)':'var(--red)'}">
          ${connected ? 'online' : 'offline'}
        </div>
        <div class="sc-sub">chain ${status?.deployments?.chain_id ?? '—'}</div>
      </div>
      <div class="sc">
        <div class="sc-label">Голосований</div>
        <div class="sc-val">${polls.length}</div>
        <div class="sc-sub">${active.length} активных</div>
      </div>
      <div class="sc">
        <div class="sc-label">Голосов on-chain</div>
        <div class="sc-val">${polls.reduce((a,p)=>a+p.total_votes,0)}</div>
        <div class="sc-sub">через ZK proofs</div>
      </div>
      <div class="sc">
        <div class="sc-label">Аккаунт</div>
        <div class="sc-val" style="font-size:1rem">
          ${me ? esc(me.nick) : '—'}
        </div>
        <div class="sc-sub">${me ? (me.approved ? '✓ в вайтлисте' : '⏳ ждёт админа') : 'не авторизован'}</div>
      </div>
    </div>

    ${!me ? `
      <div class="ib info" style="margin-bottom:1.5rem">
        Войдите или зарегистрируйтесь, чтобы участвовать.
        Пароль детерминированно превращается в приватный ключ —
        <a href="/how-it-works" style="color:var(--accent)">как это работает</a>.
        <button class="vsub" style="margin-top:.7rem" onclick="openAuthModal('register')">🔑 Войти / зарегистрироваться</button>
      </div>` : !me.approved ? `
      <div class="ib warn" style="margin-bottom:1.5rem">
        ⏳ Ваша регистрация ждёт одобрения администратора. Голосовать пока нельзя.
      </div>` : ''}

    ${active.length ? `
    <div class="sh"><div class="sh-title">Активные голосования</div></div>
    <div class="pgrid">${active.map(pollCard).join('')}</div>` : `
    <div class="empty"><div class="empty-ico">🗳</div><h3>Активных голосований нет</h3>
      <p>${me?.approved
        ? '<button class="vsub" onclick="nav(\'create\')">+ Создать опрос</button>'
        : 'Они появятся, когда участники начнут их создавать.'}</p>
    </div>`}
  </div>`;

  ROOT().querySelectorAll('.pc').forEach(c =>
    c.addEventListener('click', () => nav('poll', c.dataset.addr)));
}

/* ── POLLS LIST ───────────────────────────────────────────────────────────── */
async function renderPolls() {
  const pd = await api('GET', '/api/polls');
  const polls = pd.polls || [];
  const filtered = filter === 'all' ? polls : polls.filter(p => p.status === filter);
  const counts = { all: polls.length, active: 0, upcoming: 0, ended: 0 };
  polls.forEach(p => counts[p.status] = (counts[p.status] || 0) + 1);

  ROOT().innerHTML = `<div class="page">
    <div class="sh">
      <div class="sh-title">Все голосования</div>
      ${me?.approved ? '<button class="vsub" style="margin:0" onclick="nav(\'create\')">+ Создать опрос</button>' : ''}
    </div>
    <div class="filters">
      ${['all','active','upcoming','ended'].map(f =>
        `<button class="fb ${filter===f?'on':''}" onclick="setFilter('${f}')">${
          {all:'Все', active:'Активные', upcoming:'Скоро', ended:'Завершены'}[f]
        } ${counts[f]||0}</button>`).join('')}
    </div>
    ${filtered.length
      ? `<div class="pgrid">${filtered.map(pollCard).join('')}</div>`
      : `<div class="empty"><div class="empty-ico">🗳</div><h3>Нет голосований</h3><p>В этой категории пусто</p></div>`}
  </div>`;

  ROOT().querySelectorAll('.pc').forEach(c =>
    c.addEventListener('click', () => nav('poll', c.dataset.addr)));
}
function setFilter(f) { filter = f; renderPolls(); }
window.setFilter = setFilter;

function pollCard(p) {
  const tv = p.total_votes;
  const segs = (p.results || []).map((v, i) => {
    const w = tv > 0 ? Math.round(v / tv * 100) : Math.round(100 / (p.options_count || 2));
    const hue = 220 + i * 38;
    return `<div class="pc-seg" style="width:${w}%;background:hsl(${hue},65%,58%)"></div>`;
  }).join('');
  return `<div class="pc" data-addr="${p.address}">
    <div class="pc-top"><div class="pc-cat">#${p.poll_id}</div>${badge(p.status)}</div>
    <div class="pc-title">${esc(p.title)}</div>
    <div class="pc-meta">
      <span>🗳 ${tv}</span>
      <span>${p.status==='active' ? '⏱ '+timeLeft(p.end_time) : p.status==='upcoming' ? '→ '+timeLeft(p.start_time) : '✓ done'}</span>
    </div>
    <div class="pc-bar">${segs}</div>
  </div>`;
}

/* ── POLL DETAIL ──────────────────────────────────────────────────────────── */
async function renderPoll() {
  ROOT().innerHTML = `<div class="page"><div class="subtle-note">Загрузка…</div></div>`;
  const poll = await api('GET', `/api/polls/${pollAddr}`);
  if (!poll._ok || !poll.title) {
    ROOT().innerHTML = `<div class="page"><div class="empty"><h3>Не найдено</h3></div></div>`;
    return;
  }

  const options = poll.options || Array.from({length: poll.options_count}, (_, i) => `Вариант ${i+1}`);
  const maxV = Math.max(...(poll.results || [1]));
  const winIdx = (poll.results || []).indexOf(maxV);

  ROOT().innerHTML = `<div class="page">
    <button class="back" onclick="nav('polls')">← НАЗАД</button>
    <div class="pd-grid">
      <div>
        <div class="card" style="margin-bottom:1rem">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem;margin-bottom:.7rem">
            <div style="font-size:.67rem;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;font-family:var(--mono)">#${poll.poll_id}</div>
            ${badge(poll.status)}
          </div>
          <div class="pd-title">${esc(poll.title)}</div>
          <div class="pd-desc">${esc(poll.description || '')}</div>
          <div class="pd-chips">
            <div class="chip">🗳 ${poll.total_votes} голосов</div>
            <div class="chip">📅 ${fmtTime(poll.start_time)}</div>
            <div class="chip">⏰ ${fmtTime(poll.end_time)}</div>
            ${poll.status==='active' ? `<div class="chip" style="color:var(--green)">⏱ ${timeLeft(poll.end_time)}</div>` : ''}
            ${poll.status==='upcoming' ? `<div class="chip" style="color:var(--warn)">→ через ${timeLeft(poll.start_time)}</div>` : ''}
          </div>
        </div>

        <div class="card">
          <div class="rt">${poll.results_hidden ? 'РЕЗУЛЬТАТЫ СКРЫТЫ ДО ОКОНЧАНИЯ' : 'РЕЗУЛЬТАТЫ'}</div>
          ${poll.results_hidden ? `
            <div class="ib info" style="margin:0">
              По требованию анонимности промежуточные результаты скрыты —
              они появятся после ${fmtTime(poll.end_time)}.
            </div>` :
            options.map((opt, i) => {
              const pct = poll.percentages?.[i] ?? 0;
              const isWin = poll.status !== 'active' && i === winIdx && poll.total_votes > 0;
              return `<div class="rr">
                <div class="rr-top">
                  <div class="rr-label">${LABELS[i]}. ${esc(opt)}</div>
                  <div class="rr-nums">
                    <span class="rr-pct">${pct}%</span>
                    <span class="rr-cnt">${poll.results?.[i] || 0} г.</span>
                  </div>
                </div>
                <div class="rr-track"><div class="rr-fill ${isWin?'win':''}" style="width:${pct}%"></div></div>
              </div>`;
            }).join('')
          }
        </div>
      </div>

      <div>
        <div class="card" id="vpanel">${renderVotePanel(poll, options)}</div>
      </div>
    </div>
  </div>`;
}

function renderVotePanel(poll, options) {
  if (poll.status === 'ended') return `
    <div class="vp-title">ГОЛОСОВАНИЕ ЗАВЕРШЕНО</div>
    <div class="ib info">Голосование закрыто. Результаты записаны в блокчейн.</div>`;

  if (poll.status === 'upcoming') return `
    <div class="vp-title">СКОРО НАЧНЁТСЯ</div>
    <div class="ib warn">Откроется через ${timeLeft(poll.start_time)}.</div>`;

  if (!me) return `
    <div class="vp-title">🔐 ПРОГОЛОСОВАТЬ</div>
    <div class="ib warn">Войдите или зарегистрируйтесь, чтобы проголосовать.</div>
    <button class="vsub" onclick="openAuthModal('register')">🔑 ВОЙТИ</button>`;

  if (!me.approved) return `
    <div class="vp-title">⏳ ОЖИДАЕТ ОДОБРЕНИЯ</div>
    <div class="ib err">Ваша заявка ещё не подтверждена администратором.
      Когда вас добавят в вайтлист, вы сможете проголосовать.</div>`;

  const opts = options.map((opt, i) => `
    <button class="opt ${selOpt===i?'sel':''}" id="opt${i}" onclick="selectOpt(${i})">
      <span class="ol">${LABELS[i]}</span>
      <span>${esc(opt)}</span>
    </button>`).join('');

  return `
    <div class="vp-title">🔐 АНОНИМНОЕ ГОЛОСОВАНИЕ</div>
    <div class="opts">${opts}</div>
    <button class="vsub" id="vsub" onclick="doVote('${poll.address}')" ${selOpt===null?'disabled':''}>
      ПРОГОЛОСОВАТЬ
    </button>
    <div class="vnote">ZK-Proof • Groth16 • Merkle inclusion • Nullifier hash</div>`;
}
function selectOpt(i) {
  selOpt = i;
  document.querySelectorAll('.opt').forEach((b, j) => b.classList.toggle('sel', j === i));
  const s = $('vsub'); if (s) s.removeAttribute('disabled');
}
window.selectOpt = selectOpt;

async function doVote(addr) {
  if (selOpt === null || !me) return;
  const panel = $('vpanel');
  const steps = [
    'derive private key from your password',
    'fetch Merkle proof from API',
    'compute nullifier = poseidon(secret, pollId)',
    'build Groth16 stub proof',
    'sign & relay transaction',
  ];
  panel.innerHTML = `
    <div class="vp-title">⏳ ГЕНЕРАЦИЯ ZK-PROOF</div>
    <div class="zk-wrap">${steps.map((s, i) => `
      <div class="zk-step" id="zks${i}">
        <span style="width:10px;opacity:.3">○</span> ${s}
      </div>`).join('')}
    </div>
    <div class="vnote">Отправка в Hardhat node...</div>`;

  for (let i = 0; i < steps.length; i++) {
    await delay(280 + i * 120);
    const el = $(`zks${i}`); if (!el) break;
    el.innerHTML = `<div class="spin"></div> ${steps[i]}`;
    el.className = 'zk-step running';
    await delay(320 + i * 60);
    el.innerHTML = `<span style="color:var(--green)">✓</span> ${steps[i]}`;
    el.className = 'zk-step done';
  }
  await delay(200);

  const res = await api('POST', '/api/vote', {
    poll_address: addr,
    option_index: selOpt,
  });

  if (res.ok || res.tx_hash) {
    panel.innerHTML = `
      <div class="success-box">
        <div class="sb-icon">✓</div>
        <div class="sb-title">ГОЛОС ЗАСЧИТАН</div>
        <div style="font-size:.82rem;color:var(--text2);margin-top:.3rem">${esc(res.message || '')}</div>
        <div class="sb-hash">
          tx: ${esc(res.tx_hash || '')}<br>
          nullifier: ${esc(res.nullifier || '')}<br>
          block: ${esc(String(res.block || ''))} | gas: ${esc(String(res.gas_used || ''))}
        </div>
      </div>`;
    toast('✓ Голос записан в блокчейн!', 'ok');
    setTimeout(() => renderPoll(), 2200);
  } else {
    panel.innerHTML = `
      <div class="vp-title">⚠ ОШИБКА</div>
      <div class="ib err">${esc(res.detail || res.error || 'Неизвестная ошибка')}</div>
      <button class="vsub" onclick="renderPoll()">ПОПРОБОВАТЬ СНОВА</button>`;
    toast(res.detail || res.error, 'err');
  }
}
const delay = ms => new Promise(r => setTimeout(r, ms));

/* ── CREATE POLL ──────────────────────────────────────────────────────────── */
function renderCreate() {
  if (!me) {
    ROOT().innerHTML = `<div class="page">
      <div class="empty"><div class="empty-ico">🔐</div>
        <h3>Войдите, чтобы создавать опросы</h3>
        <p><button class="vsub" onclick="openAuthModal('register')">Войти / зарегистрироваться</button></p>
      </div></div>`;
    return;
  }
  if (!me.approved) {
    ROOT().innerHTML = `<div class="page">
      <div class="empty"><div class="empty-ico">⏳</div>
        <h3>Регистрация ждёт подтверждения</h3>
        <p>Создавать опросы могут только верифицированные участники.</p>
      </div></div>`;
    return;
  }

  ROOT().innerHTML = `<div class="page">
    <div class="sh"><div class="sh-title">Новый опрос</div></div>
    <div class="create-form">
      <div class="form-group">
        <label class="form-label">Название *</label>
        <input type="text" id="cp-title" class="form-input" maxlength="200" placeholder="Например: Лучший преподаватель семестра">
      </div>
      <div class="form-group">
        <label class="form-label">Описание</label>
        <textarea id="cp-desc" class="form-textarea" maxlength="1000" placeholder="Контекст, цель опроса, правила"></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Варианты ответа * (минимум 2)</label>
        <div id="cp-options"></div>
        <button class="add-option-btn" onclick="addOption()">+ Добавить вариант</button>
      </div>
      <div class="form-row-2">
        <div class="form-group">
          <label class="form-label">Начало через (сек)</label>
          <input type="number" id="cp-start" class="form-input" value="30" min="0" max="86400">
        </div>
        <div class="form-group">
          <label class="form-label">Длительность (сек)</label>
          <input type="number" id="cp-dur" class="form-input" value="600" min="60">
        </div>
      </div>
      <div id="cp-error" class="auth-error"></div>
      <button class="vsub" id="cp-submit" onclick="submitCreate()">ОПУБЛИКОВАТЬ ОПРОС</button>
      <div class="subtle-note">
        Опрос создаётся как смарт-контракт VotingPoll. Вы становитесь его создателем
        и можете управлять per-poll вайтлистом.
      </div>
    </div>
  </div>`;

  // Старт с двумя пустыми вариантами
  ['', ''].forEach(addOption);
}

function addOption(initial = '') {
  const wrap = $('cp-options'); if (!wrap) return;
  const idx = wrap.children.length;
  const row = document.createElement('div');
  row.className = 'option-row';
  row.innerHTML = `
    <input type="text" class="form-input cp-opt" maxlength="120" placeholder="${LABELS[idx] || ''}. Вариант ${idx+1}" value="${esc(initial)}">
    <button type="button" class="opt-remove" onclick="this.parentElement.remove()">×</button>`;
  wrap.appendChild(row);
}
window.addOption = addOption;

async function submitCreate() {
  const err = $('cp-error');
  err.classList.remove('show'); err.textContent = '';

  const title = $('cp-title').value.trim();
  const desc  = $('cp-desc').value.trim();
  const opts  = [...document.querySelectorAll('.cp-opt')]
                  .map(i => i.value.trim()).filter(Boolean);
  const start = parseInt($('cp-start').value, 10);
  const dur   = parseInt($('cp-dur').value, 10);

  if (title.length < 3) {
    err.textContent = 'Название минимум 3 символа';
    err.classList.add('show'); return;
  }
  if (opts.length < 2) {
    err.textContent = 'Минимум 2 варианта ответа';
    err.classList.add('show'); return;
  }
  if (dur < 60) {
    err.textContent = 'Длительность минимум 60 секунд';
    err.classList.add('show'); return;
  }

  const btn = $('cp-submit');
  btn.disabled = true; btn.textContent = '⏳ ДЕПЛОЙ КОНТРАКТА...';

  const r = await api('POST', '/api/polls', {
    title, description: desc, options: opts,
    start_offset_seconds: start, duration_seconds: dur,
  });

  if (r.ok) {
    toast('✓ Опрос создан и задеплоен', 'ok');
    nav('poll', r.poll_address);
  } else {
    err.textContent = r.detail || r.error || 'Ошибка'; err.classList.add('show');
    btn.disabled = false; btn.textContent = 'ОПУБЛИКОВАТЬ ОПРОС';
  }
}
window.submitCreate = submitCreate;

/* ── ADMIN ────────────────────────────────────────────────────────────────── */
async function renderAdmin() {
  if (!adminToken) {
    ROOT().innerHTML = `<div class="page">
      <div class="admin-banner locked">
        🔒 <div>
          <div style="font-weight:700;font-family:'Syne'">Админ-зона</div>
          <div style="font-size:.8rem;color:var(--text2)">
            Введите токен из файла <code>admin_token.txt</code>.
          </div>
        </div>
        <button class="vsub" style="margin-left:auto;width:auto;padding:.5rem 1.2rem" onclick="openTokenModal()">Ввести токен</button>
      </div>
    </div>`;
    return;
  }

  const status = await adminApi('GET', '/api/admin/status');
  if (!status._ok) {
    if (status.error?.includes('Token') || status.error?.includes('401') || status.error?.toLowerCase().includes('token')) {
      sessionStorage.removeItem('ac_admin_token');
      adminToken = '';
      toast('Неверный admin token', 'err');
      return renderAdmin();
    }
    ROOT().innerHTML = `<div class="page"><div class="ib err">${esc(status.error)}</div></div>`;
    return;
  }

  const [pending, approved] = await Promise.all([
    adminApi('GET', '/api/admin/users/pending'),
    adminApi('GET', '/api/admin/users/approved'),
  ]);

  const pendingList  = (pending.users  || []);
  const approvedList = (approved.users || []);

  ROOT().innerHTML = `<div class="page">
    <div class="admin-banner">
      🛡 <div>
        <div style="font-weight:700;font-family:'Syne'">Панель администратора</div>
        <div style="font-size:.8rem;opacity:.85">
          ${status.users_pending} ожидают подтверждения · ${status.users_approved} одобрено · ${status.students_whitelisted}/${status.students_total} в вайтлисте
        </div>
      </div>
      <button class="vsub" style="margin-left:auto;width:auto;padding:.4rem 1rem;background:rgba(255,255,255,.18)" onclick="logoutAdmin()">Выйти из админки</button>
    </div>

    <div style="margin-bottom:1.5rem">
      <button class="setup-btn" id="setup-btn"
        onclick="doSetup()" ${!status.node_connected||status.contracts_deployed?'disabled':''}>
        ${status.contracts_deployed ? '✓ Контракты задеплоены' : '⚡ БЫСТРЫЙ СТАРТ — задеплоить и настроить всё'}
      </button>
      ${!status.node_connected
        ? '<div class="ib warn">Запустите Hardhat: <code>cd contracts && npx hardhat node</code></div>' : ''}
    </div>

    <div class="admin-grid">
      <!-- LEFT: pending registrations -->
      <div class="admin-card">
        <div class="aca-title">🆕 Ожидают подтверждения (${pendingList.length})</div>
        ${pendingList.length ? pendingList.map(u => `
          <div class="pending-card" data-w="${u.wallet}">
            <div class="pc-info">
              <div class="pc-nick">${esc(u.nick)}</div>
              <div class="pc-wallet">${esc(u.wallet)}</div>
              <div class="pc-time">регистрация: ${u.registered_at ? fmtTime(u.registered_at) : '—'}</div>
            </div>
            <button class="pc-action" onclick="approveUser('${u.wallet}', this)">✓ В вайтлист</button>
          </div>`).join('') : '<div class="subtle-note">Никто не зарегистрировался.</div>'}
      </div>

      <!-- RIGHT: approved + status -->
      <div class="admin-card">
        <div class="aca-title">✓ Одобрены (${approvedList.length})</div>
        ${approvedList.length ? approvedList.map(u => `
          <div class="sr">
            <div class="sdot"></div>
            <div style="flex:1;min-width:0">
              <div class="sname">${esc(u.nick)}</div>
              <div class="smeta">${esc(u.wallet.slice(0,10)+'…'+u.wallet.slice(-6))}</div>
            </div>
          </div>`).join('') : '<div class="subtle-note">Ещё никто не одобрен.</div>'}
      </div>
    </div>

    <div class="sh" style="margin-top:1.5rem"><div class="sh-title">Контракты</div></div>
    <div class="admin-grid">
      <div class="admin-card">
        ${['factory','whitelist','verifier','poseidon'].map(k => `
          <div class="sr">
            <div class="sdot ${status.deployments?.[k]?'':'off'}"></div>
            <div>
              <div class="sname">${k}</div>
              <div class="smeta">${status.deployments?.[k] ? status.deployments[k].slice(0,10)+'…'+status.deployments[k].slice(-6) : 'not deployed'}</div>
            </div>
          </div>`).join('')}
      </div>

      <!-- QR -->
      <div class="qr-card">
        <div class="qr-title">📲 QR-код для одногруппников</div>
        <canvas id="qr-canvas"></canvas>
        <div class="qr-url" id="qr-url">${esc(getPublicUrl())}</div>
        <div class="subtle-note" style="margin-top:.4rem">
          Любой, кто отсканирует, попадёт на регистрацию.
        </div>
        <button class="vsub" style="width:auto;margin-top:.6rem;padding:.4rem .9rem;display:inline-block"
          onclick="changePublicUrl()">Сменить URL</button>
      </div>
    </div>

    ${status.contracts_deployed ? `
    <div style="margin-top:1rem;display:grid;grid-template-columns:1fr 1fr;gap:.5rem">
      <button class="setup-btn secondary" onclick="doSeedPolls()">+ Создать тестовые опросы</button>
      <button class="setup-btn secondary" onclick="doSync()">↻ Синхронизировать дерево</button>
    </div>` : ''}
  </div>`;

  // Рендерим QR
  drawQR();
}

function getPublicUrl() {
  return localStorage.getItem('ac_public_url') ||
         (window.AC_PUBLIC_URL && window.AC_PUBLIC_URL.length ? window.AC_PUBLIC_URL : window.location.origin);
}
function changePublicUrl() {
  const cur = getPublicUrl();
  const v = prompt('Публичный URL для QR (например, Cloudflare Tunnel):', cur);
  if (v == null) return;
  localStorage.setItem('ac_public_url', v.trim() || window.location.origin);
  drawQR();
  $('qr-url').textContent = getPublicUrl();
  toast('URL обновлён', 'ok');
}
function drawQR() {
  const canvas = $('qr-canvas'); if (!canvas || !window.QRCode) return;
  QRCode.toCanvas(canvas, getPublicUrl(), { width: 220, margin: 1, color: { dark: '#0d0f14', light: '#ffffff' } }, err => {
    if (err) console.warn('QR error:', err);
  });
}

function logoutAdmin() {
  if (!confirm('Выйти из админки?')) return;
  sessionStorage.removeItem('ac_admin_token');
  adminToken = '';
  toast('Вышли из админки');
  render();
}
window.logoutAdmin = logoutAdmin;
window.openTokenModal = openTokenModal;
window.closeTokenModal = closeTokenModal;
window.submitToken = submitToken;
window.changePublicUrl = changePublicUrl;

async function approveUser(wallet, btn) {
  btn.disabled = true; btn.textContent = '⏳ ...';
  const r = await adminApi('POST', `/api/admin/users/${wallet}/approve`);
  if (r.ok) {
    toast('✓ Добавлен в вайтлист', 'ok');
    btn.closest('.pending-card').classList.add('approved');
    setTimeout(renderAdmin, 700);
  } else {
    btn.disabled = false; btn.textContent = '✓ В вайтлист';
    toast(r.detail || r.error || 'Ошибка', 'err');
  }
}
window.approveUser = approveUser;

async function doSetup() {
  const btn = $('setup-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Деплой...'; }
  toast('Деплой контрактов...');
  const r = await adminApi('POST', '/api/admin/setup');
  if (r.ok) {
    toast('✓ Всё настроено!', 'ok');
    renderAdmin();
  } else {
    toast(r.detail || 'Ошибка при деплое', 'err');
    if (btn) { btn.disabled = false; btn.textContent = '⚡ БЫСТРЫЙ СТАРТ'; }
  }
}
window.doSetup = doSetup;

async function doSeedPolls() {
  toast('Создание опросов...');
  await adminApi('POST', '/api/admin/polls/seed');
  toast('✓ Опросы созданы', 'ok');
  renderAdmin();
}
window.doSeedPolls = doSeedPolls;

async function doSync() {
  toast('Синхронизация дерева...');
  await adminApi('POST', '/api/admin/sync');
  toast('✓ Готово', 'ok');
  renderAdmin();
}
window.doSync = doSync;

/* ── Init ─────────────────────────────────────────────────────────────────── */
window.nav             = nav;
window.openAuthModal   = openAuthModal;
window.closeAuthModal  = closeAuthModal;
window.setAuthMode     = setAuthMode;
window.doAuth          = doAuth;
window.onWalletClick   = onWalletClick;
window.doVote          = doVote;

(async () => {
  // Восстанавливаем сессию (cookie ставится сервером, нам нужно только узнать,
  // кто мы такие)
  const r = await api('GET', '/api/auth/me');
  if (r._ok && r.user) {
    me = r.user;
    updateWalletUI();
  }
  // Public URL из шаблона (через <body data-public-url>)
  const bd = document.body.dataset.publicUrl;
  if (bd) window.AC_PUBLIC_URL = bd;

  await checkStatus();
  render();
  setInterval(async () => {
    await checkStatus();
    if (me) {
      const r = await api('GET', '/api/auth/me');
      if (r._ok && r.user) {
        const wasApproved = me.approved;
        me = r.user; updateWalletUI();
        if (!wasApproved && me.approved) {
          toast('🎉 Вас одобрили! Можно голосовать.', 'ok');
          if (page === 'home' || page === 'poll') render();
        }
      }
    }
  }, 12000);
})();
