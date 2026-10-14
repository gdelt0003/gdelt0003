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

function addText(parent, tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text || '';
  parent.append(element);
  return element;
}

function addDownloadLink(parent, item) {
  const url = safeVideoUrl(item.url);
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  link.textContent = item.label;
  parent.append(link);
}

function renderMainVideos(payload) {
  const videos = Array.isArray(payload.videos) ? payload.videos : [];
  const renderableVideos = videos.filter((item) => safeVideoUrl(item?.video_url));
  $mainVideos.replaceChildren();
  $mainVideosStatus.textContent = `${renderableVideos.length} 条主视频`;

  for (const item of renderableVideos) {
    const videoUrl = safeVideoUrl(item.video_url);

    const card = document.createElement('article');
    card.className = 'main-video-card';

    const player = document.createElement('video');
    player.className = 'main-video-player';
    player.controls = true;
    player.preload = 'metadata';
    player.playsInline = true;
    const source = document.createElement('source');
    source.src = videoUrl;
    source.type = 'video/mp4';
    player.append(source);

    const content = document.createElement('div');
    content.className = 'main-video-content';
    addText(content, 'h3', 'main-video-title', item.title || '未命名主视频');
    addText(
      content,
      'p',
      'main-video-meta',
      [item.event_date, item.publisher, item.resolution].filter(Boolean).join(' · '),
    );
    if (item.render_engine) {
      const engine = addText(content, 'p', 'main-video-engine', `渲染工具：${item.render_engine}`);
      const engineUrl = safeVideoUrl(item.render_engine_url);
      if (engineUrl) {
        const attribution = document.createElement('a');
        attribution.href = engineUrl;
        attribution.textContent = '上游项目与来源';
        attribution.target = '_blank';
        attribution.rel = 'noreferrer';
        engine.append(' ', attribution);
      }
    }
    addText(content, 'p', 'main-video-review-status', item.review_status || '复核状态未登记');
    addText(content, 'p', 'main-video-note meta', item.note || '');

    const links = document.createElement('p');
    links.className = 'main-video-links';
    addDownloadLink(links, { url: item.video_url, label: '下载 MP4' });
    for (const subtitle of Array.isArray(item.subtitles) ? item.subtitles : []) {
      addDownloadLink(links, subtitle);
    }
    const sourceUrl = safeVideoUrl(item.source_url);
    if (sourceUrl) {
      const sourceLink = document.createElement('a');
      sourceLink.href = sourceUrl;
      sourceLink.textContent = '来源视频';
      sourceLink.target = '_blank';
      sourceLink.rel = 'noreferrer';
      links.append(sourceLink);
    }
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
