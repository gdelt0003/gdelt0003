const $highlightGrid = document.getElementById('highlightGrid');
const $highlightsStatus = document.getElementById('highlightsStatus');

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
    const batch = Array.isArray(payload.batch) ? payload.batch : [];
    $highlightsStatus.textContent = `${batch.length} 个白宫视频时间点 · ${payload.source_title || ''}`;
    $highlightGrid.innerHTML = batch.map((clip) => `
      <article class="video-card">
        <div class="video-info">
          <h3 class="clip-title">${clip.title}</h3>
          <div class="meta">${clip.source_channel} · ${formatTime(clip.start_sec)}–${formatTime(clip.end_sec)} · ${clip.duration_sec}s</div>
          <p class="clip-description">${clip.note || ''}</p>
          <a class="clip-link" href="${clip.play_url}" target="_blank" rel="noreferrer">在 Invidious 播放此片段时间点</a>
          <a class="source-link" href="${clip.source_url}" target="_blank" rel="noreferrer">白宫原视频</a>
        </div>
      </article>
    `).join('') || '<div class="empty">暂无默认候选。</div>';
  } catch (error) {
    console.error(error);
    $highlightsStatus.textContent = '分段链接暂不可用';
    $highlightGrid.innerHTML = '<div class="empty">Actions 尚未发布白宫分段链接，请稍后重试。</div>';
  }
}
loadHighlights();
