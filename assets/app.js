const $highlightGrid = document.getElementById('highlightGrid');
const $highlightsStatus = document.getElementById('highlightsStatus');

// Utility: escape HTML for legacy video feed rendering
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeVideo(video) {
  if (!video || typeof video !== 'object') return null;
  const title = typeof video.title === 'string' && video.title.trim() ? video.title.trim() : 'Untitled video';
  const author = typeof video.author === 'string' && video.author.trim() ? video.author.trim() : 'YouTube';
  const duration = typeof video.duration === 'string' && video.duration.trim() ? video.duration.trim() : '—';

  let url = '#';
  if (typeof video.url === 'string' && video.url.trim()) {
    try {
      const parsed = new URL(video.url.trim());
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        url = parsed.href;
      }
    } catch (error) {
      url = '#';
    }
  }

  let thumbnail = 'https://images.unsplash.com/...';
  if (typeof video.thumbnail === 'string' && video.thumbnail.trim()) {
    try {
      const parsed = new URL(video.thumbnail.trim());
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        thumbnail = parsed.href;
      }
    } catch (error) {
      thumbnail = 'https://images.unsplash.com/...';
    }
  }

  return { title, author, duration, url, thumbnail };
}

// Short-hand time formatter used by highlights UI
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

// If a generated batch manifest exists, show highlights; otherwise the repo's feed loader can be used.
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
      player.addEventListener('loadedmetadata', () => {
        if (player.videoWidth && player.videoHeight) {
          player.style.aspectRatio = `${player.videoWidth} / ${player.videoHeight}`;
        }
      });
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
      const details = [
        clip.source_channel,
        `${formatTime(clip.start_sec)}–${formatTime(clip.end_sec)}`,
        `${clip.duration_sec}s`,
        clip.output_resolution,
        clip.source_resolution ? `源 ${clip.source_resolution}` : '',
        Array.isArray(clip.subtitle_languages)
          ? '中英字幕'
          : '',
      ].filter(Boolean);
      meta.textContent = details.join(' · ');
      const description = document.createElement('p');
      description.className = 'clip-description';
      description.textContent = clip.note || '';

      const download = document.createElement('a');
      download.className = 'clip-link';
      download.href = clip.file;
      download.download = '';
      download.textContent = '下载 MP4';

      const subtitleLink = clip.subtitle_file
        ? document.createElement('a')
        : null;
      if (subtitleLink) {
        subtitleLink.className = 'subtitle-link';
        subtitleLink.href = clip.subtitle_file;
        subtitleLink.download = '';
        subtitleLink.textContent = '下载中英字幕';
      }

      const sourceLink = document.createElement('a');
      sourceLink.className = 'source-link';
      sourceLink.href = clip.source_url;
      sourceLink.target = '_blank';
      sourceLink.rel = 'noreferrer';
      sourceLink.textContent = '白宫原视频';

      info.append(title, meta, description, download);
      if (subtitleLink) info.append(subtitleLink);
      info.append(sourceLink);
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

// Try highlights first; if that fails, the repository may expose a generic feed endpoint.
(async function init() {
  try {
    await loadHighlights();
  } catch (e) {
    // fallback: leave space for the legacy feed loader (which is rendered server-side in some branches)
    console.warn('Highlights loader failed, leaving legacy feed UI in place', e);
  }
})();
