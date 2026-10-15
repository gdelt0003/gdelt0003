const $sourceDetails = document.getElementById('mainVideoSourceDetails');
const $sourceStatus = document.getElementById('mainVideoSourceStatus');
const $sourceTitle = document.getElementById('mainVideoSourceTitle');
const $sourceMeta = document.getElementById('mainVideoSourceMeta');
const $artifactDetails = document.getElementById('mainVideoArtifactDetails');
const requestedVideoId = $sourceDetails?.getAttribute('data-video-id');

function safeSourceUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value.trim(), document.baseURI);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function addSourceText(parent, tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text || '';
  parent.append(element);
  return element;
}

function addArtifactLink(parent, urlValue, label) {
  const url = safeSourceUrl(urlValue);
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  link.textContent = label;
  link.target = '_blank';
  link.rel = 'noreferrer';
  parent.append(link);
}

function renderArtifactDetails(video) {
  $artifactDetails.replaceChildren();
  addSourceText(
    $artifactDetails,
    'p',
    'main-video-artifact-status',
    video.review_status || '预览复核状态未登记',
  );
  if (video.render_engine) {
    addSourceText($artifactDetails, 'p', 'main-video-artifact-renderer', `处理工具: ${video.render_engine}`);
  }
  if (video.source_sha256) {
    addSourceText($artifactDetails, 'p', 'main-video-artifact-hash', `源文件 SHA-256: ${video.source_sha256}`);
  }
  if (video.note) addSourceText($artifactDetails, 'p', 'main-video-artifact-note', video.note);

  const links = document.createElement('p');
  links.className = 'main-video-artifact-links';
  addArtifactLink(links, video.preview_release_url, '预览 Release');
  addArtifactLink(links, video.manifest_url, '处理清单');
  addArtifactLink(links, video.operation_audit_url, '操作审计');
  addArtifactLink(links, video.source_url, '原始来源视频');
  for (const subtitle of Array.isArray(video.subtitles) ? video.subtitles : []) {
    addArtifactLink(links, subtitle.url, subtitle.label || '字幕文件');
  }
  if (links.children.length) $artifactDetails.append(links);

  if (video.subtitle_layout_request) {
    const layout = video.subtitle_layout_request;
    addSourceText(
      $artifactDetails,
      'p',
      'main-video-artifact-layout',
      `字幕布局: ${layout.profile || '未指定'} · ${layout.status || '状态未登记'} · 画面复核: ${layout.visual_render_review || '未核验'}。${layout.contract || ''} ${layout.source_graphics || ''}`,
    );
  }
}

function renderSourceDetails(payload) {
  const videos = Array.isArray(payload.videos) ? payload.videos : [];
  const video = videos.find((item) => item.id === requestedVideoId);
  if (!video || !video.provenance || !Array.isArray(video.provenance.sources)) {
    $sourceStatus.textContent = '未找到此事件的视频来源记录';
    $sourceDetails.textContent = '来源与版本信心资料暂不可用。';
    return;
  }

  $sourceTitle.textContent = video.title || '未命名主视频';
  $sourceMeta.textContent = [video.event_date, video.publisher, video.resolution]
    .filter(Boolean)
    .join(' · ');
  renderArtifactDetails(video);
  const sources = MainVideoRanking.rank(video.provenance.sources);
  $sourceStatus.textContent = `显示 ${sources.length} 条候选来源（最多 10 条）`;
  $sourceDetails.replaceChildren();

  addSourceText(
    $sourceDetails,
    'p',
    'main-video-source-ranking-method',
    video.provenance.ranking_method
      || '官方事件锚点始终保留并置顶；其余候选按事件匹配状态 → 内嵌图文状态 → 分辨率 → 时长 → 播放量排序。缺失值不补估，同级保持清单顺序。来源信任评分口径未定义，暂不参与排序。',
  );
  if (video.provenance.search_method) {
    addSourceText($sourceDetails, 'p', 'main-video-source-search-method', `检索方法: ${video.provenance.search_method}`);
  }

  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const card = document.createElement('article');
    card.className = 'main-video-source';

    addSourceText(card, 'span', 'source-rank', `#${index + 1}`);
    const sourceUrl = safeSourceUrl(source.url);
    if (sourceUrl) {
      const link = document.createElement('a');
      link.href = sourceUrl;
      link.textContent = source.title || source.publisher || source.id || '来源链接';
      link.target = '_blank';
      link.rel = 'noreferrer';
      card.append(link);
    } else {
      addSourceText(card, 'span', 'main-video-source-title', source.title || source.id || '来源链接未提供');
    }

    addSourceText(
      card,
      'span',
      `source-trust ${String(source.classification || '').toLowerCase()}`,
      MainVideoRanking.statusLabel(source.classification),
    );
    if (source.rights) addSourceText(card, 'span', 'source-rights', source.rights);

    const duration = Number.isFinite(source.duration_seconds) && source.duration_seconds >= 0
      ? `${Math.floor(source.duration_seconds / 60)}:${String(Math.floor(source.duration_seconds % 60)).padStart(2, '0')}`
      : '时长未知';
    addSourceText(
      card,
      'p',
      'main-video-source-meta',
      [
        source.hosting_platform || '托管平台未知',
        source.publisher || '发布方未知',
        source.max_resolution || '分辨率未知',
        duration,
        Number.isFinite(source.view_count) && source.view_count >= 0
          ? `${source.view_count} 次观看`
          : '播放量未知',
      ].join(' · '),
    );
    addSourceText(
      card,
      'p',
      'main-video-source-times',
      `上传时间: ${source.upload_date || '未核实'} · 发布时间: ${source.publish_date || '未核实'} · 事件时间: ${source.event_time || '未核实'}`,
    );
    addSourceText(
      card,
      'p',
      'main-video-source-overlay-status',
      `内嵌横幅/标志: ${MainVideoRanking.overlayLabel(source.overlay_status)}`,
    );
    addSourceText(
      card,
      'p',
      'main-video-source-occlusion-status',
      `遮挡评估: ${
        source.occlusion_status === 'face_not_obstructed'
          ? '记录为未遮挡人脸（仅限已观察部分）'
          : '未核验'
      }`,
    );
    if (Array.isArray(source.captions) && source.captions.length) {
      addSourceText(
        card,
        'p',
        'main-video-source-captions',
        `字幕: ${source.captions.map((caption) => caption.label || caption.language || '未标注').join(', ')}`,
      );
    }
    if (source.overlay_assessment) {
      addSourceText(card, 'p', 'main-video-source-overlay', `内嵌图文观察: ${source.overlay_assessment}`);
    }
    if (source.notes) addSourceText(card, 'p', 'main-video-source-notes meta', source.notes);
    addSourceText(
      card,
      'p',
      'main-video-source-trust-note',
      `来源信任评分: ${
        source.source_trust_note
          || (Number.isFinite(source.source_trust_score)
            ? `记录的分值 ${source.source_trust_score}（评分口径未提供）`
            : '未评分（评分口径未提供）')
      }`,
    );

    const captionProvenance = source.caption_provenance || {};
    const captionDetails = [`字幕状态: ${captionProvenance.verification || '来源轨道/审校状态未核实'}`];
    if (typeof captionProvenance.user_given_reference_score === 'number') {
      captionDetails.push(`用户参考字幕分: ${captionProvenance.user_given_reference_score}/100`);
    }
    if (captionProvenance.user_score_note) captionDetails.push(captionProvenance.user_score_note);
    addSourceText(card, 'p', 'main-video-source-captions-provenance meta', captionDetails.join(' · '));
    addSourceText(
      card,
      'p',
      'main-video-source-rights',
      `复用权利: ${source.reuse_rights_note || '未核实（未判断可否复用）'}`,
    );
    if (Array.isArray(source.checked_fields) && source.checked_fields.length) {
      addSourceText(card, 'p', 'main-video-source-checked-fields', `核验字段: ${source.checked_fields.join(', ')}`);
    } else {
      addSourceText(card, 'p', 'main-video-source-checked-fields', '核验字段: 未提供');
    }

    $sourceDetails.append(card);
  }
}

async function loadSourceDetails() {
  try {
    const response = await fetch('../../outputs/main-videos.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Main video catalog HTTP ${response.status}`);
    renderSourceDetails(await response.json());
  } catch (error) {
    console.error('Unable to load main video source details', error);
    $sourceStatus.textContent = '来源记录暂不可用';
    $sourceDetails.textContent = '来源与版本信心资料暂不可用，请稍后重试。';
  }
}

loadSourceDetails();
