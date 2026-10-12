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

async function loadHighlights() {
  try {
    const outputDirectory = './outputs/whitehouse-oct-06-2026/';
    const response = await fetch(`${outputDirectory}manifest.json`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Bilingual shorts manifest is unavailable');
    const payload = await response.json();
    const highlights = Array.isArray(payload.highlights) ? payload.highlights : [];
    const clips = highlights.flatMap((highlight) =>
      (Array.isArray(highlight.variants) ? highlight.variants : []).map((variant) => ({
        ...variant,
        id: highlight.id,
        title: highlight.title,
        start: highlight.start,
        end: highlight.end,
        source: highlight.source_video || payload.source?.url,
        subtitles: `${outputDirectory}${highlight.subtitles}`,
      })),
    );
    $highlightsStatus.textContent = `${clips.length} 支双风格短片 · ${payload.source?.title || ''}`;
    $highlightGrid.replaceChildren();
    for (const clip of clips) {
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
      title.textContent = `${clip.title} · ${clip.style === 'punchy' ? 'Punchy' : 'Editorial'}`;
      const meta = document.createElement('div');
      meta.className = 'meta';
      const details = [
        `原片 ${formatTime(clip.start)}–${formatTime(clip.end)}`,
        `${clip.duration_seconds}s`,
        clip.resolution,
        '中英硬字幕',
      ].filter(Boolean);
      meta.textContent = details.join(' · ');
      const description = document.createElement('p');
      description.className = 'clip-description';
      description.textContent = '白宫官方视频精选片段 · 英文自动转写及简体中文翻译';

      const download = document.createElement('a');
      download.className = 'clip-link';
      download.href = `${outputDirectory}${clip.file}`;
      download.download = '';
      download.textContent = '下载 MP4';

      const subtitleLink = document.createElement('a');
      subtitleLink.className = 'subtitle-link';
      subtitleLink.href = clip.subtitles;
      subtitleLink.download = '';
      subtitleLink.textContent = '下载中英字幕';

      const sourceLink = document.createElement('a');
      sourceLink.className = 'source-link';
      sourceLink.href = clip.source;
      sourceLink.target = '_blank';
      sourceLink.rel = 'noreferrer';
      sourceLink.textContent = '白宫原视频';

      info.append(title, meta, description, download);
      info.append(subtitleLink);
      info.append(sourceLink);
      card.append(player, info);
      $highlightGrid.append(card);
    }
    if (clips.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = '暂无已生成的视频。';
      $highlightGrid.append(empty);
    }
  } catch (error) {
    console.error(error);
    $highlightsStatus.textContent = '短片清单暂不可用';
    $highlightGrid.textContent = '高清双语短片暂不可用，请稍后重试。';
  }
}

loadHighlights();
