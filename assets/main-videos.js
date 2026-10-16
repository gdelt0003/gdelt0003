const $mainVideos = document.getElementById('mainVideos');
const $mainVideosStatus = document.getElementById('mainVideosStatus');

function safeVideoUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value.trim(), document.baseURI);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function addLink(parent, urlValue, label, className = '') {
  const url = safeVideoUrl(urlValue);
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  link.textContent = label;
  if (className) link.className = className;
  if (url.startsWith('https://') && !url.startsWith(document.baseURI)) {
    link.target = '_blank';
    link.rel = 'noreferrer';
  }
  parent.append(link);
}

function renderMainVideos(payload) {
  const videos = Array.isArray(payload.videos) ? payload.videos : [];
  const renderableVideos = videos
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => safeVideoUrl(item?.video_url))
    .sort((left, right) => {
      const leftDate = Date.parse(`${left.item.event_date || ''}T00:00:00Z`);
      const rightDate = Date.parse(`${right.item.event_date || ''}T00:00:00Z`);
      const leftTime = Number.isFinite(leftDate) ? leftDate : -1;
      const rightTime = Number.isFinite(rightDate) ? rightDate : -1;
      return rightTime - leftTime || left.index - right.index;
    });

  $mainVideos.replaceChildren();
  $mainVideosStatus.textContent = `${renderableVideos.length} 条主视频`;

  for (const { item } of renderableVideos) {
    const card = document.createElement('article');
    card.className = 'main-video-card';

    const player = document.createElement('video');
    player.className = 'main-video-player';
    player.controls = true;
    player.preload = 'metadata';
    player.playsInline = true;
    const source = document.createElement('source');
    source.src = safeVideoUrl(item.video_url);
    source.type = 'video/mp4';
    player.append(source);

    const content = document.createElement('div');
    content.className = 'main-video-content';
    const title = document.createElement('h3');
    title.className = 'main-video-title';
    title.textContent = item.title || '未命名主视频';
    content.append(title);

    const metadata = document.createElement('p');
    metadata.className = 'main-video-meta';
    metadata.textContent = [
      item.event_date,
      item.publisher,
      item.resolution,
      Number.isFinite(item.duration_seconds) ? `${Math.floor(item.duration_seconds / 60)} 分钟` : '',
    ].filter(Boolean).join(' · ');
    content.append(metadata);

    const status = document.createElement('p');
    status.className = 'main-video-review-status';
    status.textContent = item.homepage_status || '复核状态未登记';
    content.append(status);

    const links = document.createElement('p');
    links.className = 'main-video-links';
    addLink(links, item.source_url, '来源视频');
    addLink(links, item.source_details_url, '视频源与视频本身可信度详情');
    addLink(links, item.video_url, '下载 MP4');
    content.append(links);

    card.append(player, content);
    $mainVideos.append(card);
  }

  if ($mainVideos.children.length === 0) {
    $mainVideosStatus.textContent = '暂无可播放主视频';
    $mainVideos.textContent = '尚无已登记的主视频。';
  }
}

async function loadMainVideos() {
  try {
    const response = await fetch('outputs/main-videos.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Main video catalog HTTP ${response.status}`);
    renderMainVideos(await response.json());
  } catch (error) {
    console.error('Unable to load the main video catalog', error);
    $mainVideosStatus.textContent = '主视频清单暂不可用';
    $mainVideos.textContent = '主视频暂不可用，请稍后重试。';
  }
}

loadMainVideos();
