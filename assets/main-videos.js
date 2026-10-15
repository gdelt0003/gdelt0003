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
    if (item.subtitle_layout_request) {
      const layout = item.subtitle_layout_request;
      const layoutPanel = document.createElement('section');
      layoutPanel.className = 'main-video-layout-request';
      addText(layoutPanel, 'h4', 'main-video-layout-heading', '字幕布局要求');
      addText(
        layoutPanel,
        'p',
        'main-video-layout-status',
        `配置：${layout.profile || '未知'} · ${layout.status || '状态未登记'} · 画面复核：${layout.visual_render_review || 'not_verified'}`,
      );
      addText(layoutPanel, 'p', 'main-video-layout-contract', layout.contract || '');
      addText(layoutPanel, 'p', 'main-video-layout-source-graphics', layout.source_graphics || '');
      content.append(layoutPanel);
    }

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

    // Render provenance/source cards when available
    if (item.provenance && Array.isArray(item.provenance.sources) && item.provenance.sources.length) {
      const sourcesWrap = document.createElement('div');
      sourcesWrap.className = 'main-video-sources';
      addText(sourcesWrap, 'h4', 'sources-heading', '来源与证据');

      // compute a simple top-10 ranking by view_count (descending). preserve original order when view_count missing
      const sortedSources = Array.isArray(item.provenance.sources)
        ? [...item.provenance.sources].sort((a, b) => (b.view_count || 0) - (a.view_count || 0))
        : [];
      const topList = sortedSources.slice(0, 10);

      for (let i = 0; i < topList.length; i += 1) {
        const s = topList[i];
        const sCard = document.createElement('div');
        sCard.className = 'main-video-source';

        // rank badge
        const rank = document.createElement('span');
        rank.className = 'source-rank';
        rank.textContent = `#${i + 1}`;
        sCard.append(rank);

        // title / link
        const sLink = document.createElement('a');
        sLink.href = safeVideoUrl(s.url) || '#';
        sLink.target = '_blank';
        sLink.rel = 'noreferrer';
        sLink.textContent = s.title || s.publisher || s.id;
        sCard.append(sLink);

        // trust badge
        const trust = document.createElement('span');
        trust.className = `source-trust ${String(s.classification || '').toLowerCase()}`;
        trust.textContent = s.classification || 'unknown';
        sCard.append(trust);

        // rights badge (separate from trust/provenance)
        if (s.rights) {
          const rights = document.createElement('span');
          rights.className = 'source-rights';
          rights.textContent = s.rights;
          sCard.append(rights);
        }

        const duration = Number.isFinite(s.duration_seconds)
          ? `${Math.floor(s.duration_seconds / 60)}:${String(Math.floor(s.duration_seconds % 60)).padStart(2, '0')}`
          : '时长未知';
        const metaParts = [
          s.hosting_platform || '托管平台未知',
          s.publisher || '发布方未知',
          s.max_resolution || '分辨率未知',
          duration,
          Number.isFinite(s.view_count) ? `${s.view_count} views` : '播放量未知',
        ];
        if (metaParts.length) addText(sCard, 'p', 'main-video-source-meta', metaParts.join(' · '));

        addText(
          sCard,
          'p',
          'main-video-source-times',
          `上传时间: ${s.upload_date || '未核实'} · 发布时间: ${s.publish_date || '未核实'} · 事件时间: ${s.event_time || '未核实'}`,
        );
        if (Array.isArray(s.captions) && s.captions.length) {
          addText(sCard, 'p', 'main-video-source-captions', `字幕: ${s.captions.map((c) => c.label || c.language).join(', ')}`);
        }
        if (s.overlay_assessment) addText(sCard, 'p', 'main-video-source-overlay', `画面评估: ${s.overlay_assessment}`);
        if (s.notes) addText(sCard, 'p', 'main-video-source-notes meta', s.notes);

        // source trust note (separate from numeric score)
        addText(
          sCard,
          'p',
          'main-video-source-trust-note',
          `来源信任评分: ${s.source_trust_note || '未评分（评分口径未提供）'}`,
        );

        // caption provenance details: preserve user-given reference score separately
        const cp = s.caption_provenance || {};
        const captionParts = [
          `字幕状态: ${cp.verification || '来源轨道/审校状态未核实'}`,
        ];
        if (typeof cp.user_given_reference_score === 'number') {
          captionParts.push(`用户参考字幕分: ${cp.user_given_reference_score}/100`);
        }
        if (cp.user_score_note) captionParts.push(cp.user_score_note);
        addText(
          sCard,
          'p',
          'main-video-source-captions-provenance meta',
          captionParts.join(' · '),
        );

        addText(
          sCard,
          'p',
          'main-video-source-rights',
          `复用权利: ${s.reuse_rights_note || '未核实（未判断可否复用）'}`,
        );

        sourcesWrap.append(sCard);
      }

      content.append(sourcesWrap);
    }

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
