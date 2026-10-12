const DEFAULT_BACKEND_URL = window.SHORTS_BACKEND_URL || '/api/v1/shorts/confirm';

const state = {
  data: [],
  authorized: true
};

const els = {
  videoGrid: document.querySelector('#video-grid'),
  totalCount: document.querySelector('#total-count'),
  batchOutput: document.querySelector('#batch-output'),
  authStatus: document.querySelector('#auth-status'),
  statusPill: document.querySelector('#status-pill'),
  loadDefaultBatch: document.querySelector('#load-default-batch'),
  confirmBatch: document.querySelector('#confirm-batch'),
  toast: document.querySelector('#toast')
};

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

function showToast(message, isError = false) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.classList.toggle('error', isError);
  els.toast.classList.add('visible');
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => {
    els.toast.classList.remove('visible');
  }, 2600);
}

function renderBatch(items) {
  const batch = items.slice(0, 3).map((item) => ({
    title: item.title,
    start: formatTime(item.start_sec),
    end: formatTime(item.end_sec)
  }));

  els.batchOutput.innerHTML = batch.map((item) => `<li>${item.title} · ${item.start}–${item.end}</li>`).join('');
}

function renderCards(items) {
  els.totalCount.textContent = String(items.length);
  els.statusPill.textContent = state.authorized ? 'ready' : 'preview';
  els.authStatus.textContent = state.authorized ? '已生成默认批次，可直接提交到后台确认' : '预览模式：仅展示候选，不提交内容';
  document.querySelector('.auth-dot').style.background = state.authorized ? '#34d399' : '#fbbf24';

  if (!items.length) {
    els.videoGrid.innerHTML = '<article class="video-card"><div class="video-body"><h3 class="video-title">暂无候选</h3></div></article>';
    return;
  }

  els.videoGrid.innerHTML = items.map((item) => {
    const sourceChannel = item.source_channel || item.source_title || 'White House';
    return `
      <article class="video-card">
        <div class="video-thumb" aria-label="${item.title}"></div>
        <div class="video-body">
          <div class="video-header">
            <h3 class="video-title">${item.title}</h3>
            <span class="score-tag">${item.score}</span>
          </div>
          <div class="video-meta">${sourceChannel} · ${formatTime(item.start_sec)}–${formatTime(item.end_sec)} · ${item.status}</div>
          <p>${item.note}</p>
          <div class="tag-list">${(item.tags || []).map((tag) => `<span class="tag">#${tag}</span>`).join('')}</div>
        </div>
      </article>
    `;
  }).join('');
}

function renderAll(items) {
  renderCards(items);
  renderBatch(items);
}

async function loadHighlights() {
  try {
    const response = await fetch('./data/generated/default_batch.json');
    if (!response.ok) {
      throw new Error('default batch file not found');
    }
    const payload = await response.json();
    const data = Array.isArray(payload) ? payload : (payload.batch || []);
    state.data = Array.isArray(data) ? data : [];
    renderAll(state.data);
  } catch (error) {
    console.error(error);
    showToast('默认批次读取失败，已回退到静态空状态', true);
    state.data = [];
    renderAll([]);
  }
}

async function submitConfirmation() {
  if (!state.data.length) {
    showToast('当前没有默认批次可确认', true);
    return;
  }

  const payload = {
    event: 'default_short_batch_confirm',
    source: 'pages-default-batch',
    batch: state.data,
    confirmed_at: new Date().toISOString()
  };

  try {
    const response = await fetch(DEFAULT_BACKEND_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error('backend confirm rejected');
    }

    const result = await response.json();
    const message = result?.message || '默认批次已确认；后台已收到请求';
    showToast(message);
  } catch (error) {
    console.error(error);
    showToast('页面已记录确认，但后台地址未可用。请将 /api/v1/shorts/confirm 配置到实际后端。', true);
  }
}

els.loadDefaultBatch.addEventListener('click', () => {
  state.authorized = true;
  loadHighlights();
});

els.confirmBatch.addEventListener('click', submitConfirmation);

loadHighlights();
