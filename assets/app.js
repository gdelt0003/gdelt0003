const API = './videos.json';
const $grid = document.getElementById('videoGrid');
const $status = document.getElementById('status');
const $refresh = document.getElementById('refreshBtn');

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

async function loadVideos() {
  $status.textContent = 'Loading latest data…';
  try {
    const res = await fetch(API, { cache: 'no-store' });
    if (!res.ok) throw new Error('Unable to fetch feed');
    const videos = await res.json();
    const safeVideos = Array.isArray(videos) ? videos.map(normalizeVideo).filter(Boolean) : [];

    if (!safeVideos.length) {
      $grid.innerHTML = '<div class="empty">No videos yet. Update the YouTube URL in the workflow settings.</div>';
      $status.textContent = 'No videos available';
      return;
    }

    $grid.innerHTML = safeVideos.map(video => `
      <article class="video-card">
        <img src="${escapeHtml(video.thumbnail)}" alt="${escapeHtml(video.title)}" loading="lazy" />
        <div class="video-info">
          <h2><a href="${escapeHtml(video.url)}" target="_blank" rel="noreferrer">${escapeHtml(video.title)}</a></h2>
          <div class="meta">${escapeHtml(video.author)} • ${escapeHtml(video.duration)}</div>
        </div>
      </article>
    `).join('');
    $status.textContent = `Updated: ${safeVideos.length} videos`;
  } catch (error) {
    $grid.innerHTML = '<div class="empty">Failed to load data. Please check the workflow or YOUTUBE_URL.</div>';
    $status.textContent = 'Load failed';
  }
}

$refresh.addEventListener('click', loadVideos);
loadVideos();
