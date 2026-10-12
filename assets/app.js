const API = './videos.json';
const $grid = document.getElementById('videoGrid');
const $status = document.getElementById('status');
const $refresh = document.getElementById('refreshBtn');
const $highlightGrid = document.getElementById('highlightGrid');
const $highlightsStatus = document.getElementById('highlightsStatus');
const $confirmBatch = document.getElementById('confirmBatchBtn');
const $confirmStatus = document.getElementById('confirmStatus');
let defaultBatch = [];

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

async function loadHighlights() {
  try {
    const response = await fetch('./generated/default_batch.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Default batch manifest is unavailable');
    const payload = await response.json();
    defaultBatch = Array.isArray(payload.batch) ? payload.batch : [];
    $highlightsStatus.textContent = `${defaultBatch.length} 个候选 · ${payload.message || '批次已就绪'}`;
    $highlightGrid.innerHTML = defaultBatch.map((clip) => `
      <article class="video-card">
        ${clip.file ? `<video class="highlight-video" controls preload="metadata" src="${clip.file}"></video>` : ''}
        <div class="video-info">
          <h3 class="clip-title">${clip.title}</h3>
          <div class="meta">${clip.source_channel || 'YouTube'} · ${formatTime(clip.start_sec)}–${formatTime(clip.end_sec)} · ${clip.status || 'ready'}</div>
          <p class="clip-description">${clip.note || ''}</p>
        </div>
      </article>
    `).join('') || '<div class="empty">暂无默认候选。</div>';
  } catch (error) {
    console.error(error);
    $highlightsStatus.textContent = '默认批次暂不可用';
    $highlightGrid.innerHTML = '<div class="empty">请在 GitHub Actions 中重新生成默认批次。</div>';
  }
}

async function confirmBatch() {
  const endpoint = window.SHORTS_CONFIRM_ENDPOINT;
  if (!defaultBatch.length) {
    $confirmStatus.textContent = '当前没有可确认的默认批次。';
    return;
  }
  if (!endpoint) {
    $confirmStatus.textContent = 'Pages 是静态站点，后台确认接口尚未配置；此操作未提交。';
    return;
  }
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event: 'default_short_batch_confirm',
        source: 'github-pages',
        batch: defaultBatch,
        confirmed_at: new Date().toISOString()
      })
    });
    if (!response.ok) throw new Error(`Confirmation rejected (${response.status})`);
    $confirmStatus.textContent = '默认批次已提交确认。';
  } catch (error) {
    console.error(error);
    $confirmStatus.textContent = '后台确认失败，请稍后重试。';
  }
}

async function loadVideos() {
  $status.textContent = 'Loading latest data…';
  try {
    const res = await fetch(API, { cache: 'no-store' });
    if (!res.ok) throw new Error('Unable to fetch feed');
    const videos = await res.json();
    if (!Array.isArray(videos) || !videos.length) {
      $grid.innerHTML = '<div class="empty">No videos yet. Update the YouTube URL in the workflow settings.</div>';
      $status.textContent = 'No videos available';
      return;
    }
    $grid.innerHTML = videos.map(video => `
      <article class="video-card">
        <img src="${video.thumbnail || 'https://images.unsplash.com/...'}" alt="${video.title || 'Video'}" />
        <div class="video-info">
          <h2><a href="${video.url}" target="_blank" rel="noreferrer">${video.title}</a></h2>
          <div class="meta">${video.author || 'YouTube'} • ${video.duration || '—'}</div>
        </div>
      </article>
    `).join('');
    $status.textContent = `Updated: ${videos.length} videos`;
  } catch (error) {
    $grid.innerHTML = '<div class="empty">Failed to load data. Please check the workflow or YOUTUBE_URL.</div>';
    $status.textContent = 'Load failed';
  }
}

$refresh.addEventListener('click', loadVideos);
$confirmBatch.addEventListener('click', confirmBatch);
loadVideos();
loadHighlights();
