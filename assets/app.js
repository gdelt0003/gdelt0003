const API = './videos.json';
const $grid = document.getElementById('videoGrid');
const $status = document.getElementById('status');
const $refresh = document.getElementById('refreshBtn');

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
loadVideos();
