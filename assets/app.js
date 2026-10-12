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
    $highlightsStatus.textContent = `${batch.length} 个已剪辑 MP4 · ${payload.source_title || ''}`;
    $highlightGrid.replaceChildren();
    for (const clip of batch) {
      const card = document.createElement('article');
      card.className = 'video-card';

      const player = document.createElement('video');
      player.className = 'clip-player';
      player.controls = true;
      player.preload = 'metadata';
      player.playsInline = true;
      const source = document.createElement('source');
      source.src = clip.file;
      source.type = 'video/mp4';
      player.append(source);

      const info = document.createElement('div');
      info.className = 'video-info';
      const title = document.createElement('h3');
      title.className = 'clip-title';
      title.textContent = clip.title;
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = `${clip.source_channel} · ${formatTime(clip.start_sec)}–${formatTime(clip.end_sec)} · ${clip.duration_sec}s`;
      const description = document.createElement('p');
      description.className = 'clip-description';
      description.textContent = clip.note || '';

      const download = document.createElement('a');
      download.className = 'clip-link';
      download.href = clip.file;
      download.download = '';
      download.textContent = '下载 MP4';

      const sourceLink = document.createElement('a');
      sourceLink.className = 'source-link';
      sourceLink.href = clip.source_url;
      sourceLink.target = '_blank';
      sourceLink.rel = 'noreferrer';
      sourceLink.textContent = '白宫原视频';

      info.append(title, meta, description, download, sourceLink);
      card.append(player, info);
      $highlightGrid.append(card);
    }
    if (batch.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = '暂无已生成的视频。';
      $highlightGrid.append(empty);
    }
  } catch (error) {
    console.error(error);
    $highlightsStatus.textContent = '分段链接暂不可用';
    $highlightGrid.textContent = 'Actions 尚未发布白宫剪辑视频，请稍后重试。';
  }
}
loadHighlights();
