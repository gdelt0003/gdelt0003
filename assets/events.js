const $eventCatalog = document.getElementById('eventCatalog');
const $eventDiscovery = document.getElementById('eventDiscovery');
const $eventDiscoveryStatus = document.getElementById('eventDiscoveryStatus');
const $publishedEvents = document.getElementById('publishedEvents');
const $publishedEventsStatus = document.getElementById('publishedEventsStatus');

function eventText(value, fallback = '未核实') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function safeHttpUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const parsed = new URL(value, document.baseURI);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function eventLink(url, label) {
  const link = document.createElement('a');
  const safeUrl = safeHttpUrl(url);
  if (safeUrl) {
    link.href = safeUrl;
    link.target = '_blank';
    link.rel = 'noreferrer';
  } else {
    link.setAttribute('aria-disabled', 'true');
  }
  link.textContent = label;
  return link;
}

function sourceStatus(source) {
  const match = source.match_status || 'unverified';
  const clean = source.clean_source_status || 'unverified';
  if (match === 'verified_event_anchor') return '官方事件锚点；素材画面未必干净';
  if (match.includes('same_event_contiguous_speech_observed')) {
    return '已核同场、讲话相邻衔接；精确偏移/机位未核实';
  }
  if (match.includes('same_speech_moment_observed')) {
    return clean === 'passed' ? '同一发言时刻；干净状态通过' : '同一发言时刻线索；未通过干净源检查';
  }
  if (match.includes('same_event_scene_verified')) return '已核实同场；非精确同一发言时刻';
  if (match.includes('same_event_speech_context_verified')) return '已核实同一演讲上下文；精确时刻 / 来源链未核实';
  if (match.includes('same_speech_moment_observed_same_angle')) return '同一发言时刻；同角度/同源候选，非独立机位';
  if (match === 'related_story_only') return '相关报道，不是已核实的同事件源';
  return '候选线索；未核实匹配时刻 / 画面 / 来源链';
}

function renderCatalog(catalog) {
  $eventCatalog.replaceChildren();
  for (const event of catalog.events || []) {
    const card = document.createElement('article');
    card.className = 'event-card';
    const title = document.createElement('h3');
    title.textContent = event.identity?.title || '未命名事件';
    const identity = document.createElement('p');
    identity.className = 'event-identity';
    const details = event.identity || {};
    const identityParts = [
      `身份：${eventText(event.identity_status)}`,
      `事件日期：${eventText(details.event_date, '未知（不可用上传日替代）')}`,
      `地点：${eventText(details.location)}`,
      `Event ID：${eventText(event.event_id, '未分配：缺少可确认的身份字段')}`,
      `${(event.sources || []).length} 个来源条目`,
    ];
    identity.textContent = identityParts.join(' · ');
    const list = document.createElement('ul');
    list.className = 'event-source-list';
    const sources = event.sources || [];
    for (const source of sources) {
      const item = document.createElement('li');
      const link = eventLink(source.url, `${source.publisher || '来源'}：${source.title || source.url}`);
      const status = document.createElement('span');
      status.className = 'meta';
      status.textContent = sourceStatus(source);
      const evidence = document.createElement('small');
      evidence.textContent = source.evidence || '无直接画面证据。';
      item.append(link, status, evidence);
      list.append(item);
    }
    const sourceDetails = document.createElement('details');
    sourceDetails.className = 'event-sources-details';
    const summary = document.createElement('summary');
    summary.textContent = `查看 ${sources.length} 条来源与核验依据`;
    sourceDetails.append(summary, list);
    card.append(title, identity, sourceDetails);
    $eventCatalog.append(card);
  }
}

function renderDiscovery(discoverySets) {
  const leads = discoverySets.flatMap(({ kind, payload }) => (
    Array.isArray(payload.leads) ? payload.leads.map(lead => ({ kind, lead, checkedAt: payload.checked_at_utc })) : []
  ));
  $eventDiscovery.replaceChildren();
  const videoCount = leads.filter(item => item.kind === 'video').length;
  const articleCount = leads.filter(item => item.kind === 'article').length;
  $eventDiscoveryStatus.textContent = `${videoCount} 条白宫视频线索 · ${articleCount} 条 GDELT 文章线索`;
  for (const { kind, lead, checkedAt } of leads) {
    const item = document.createElement('article');
    item.className = 'discovery-card';
    item.append(eventLink(lead.url, lead.title || lead.video_id || lead.publisher || '未命名来源'));
    const metadata = document.createElement('p');
    metadata.className = 'meta';
    metadata.textContent = kind === 'article'
      ? [
        lead.publisher,
        lead.seen_date_utc_metadata ? `文章收录元数据 ${lead.seen_date_utc_metadata}` : '',
        '文章标题和收录日期不证明事件发生',
      ].filter(Boolean).join(' · ')
      : [
        lead.publisher,
        lead.upload_date_metadata ? `上传元数据 ${lead.upload_date_metadata}` : '',
        Number.isFinite(lead.duration_seconds) ? `${Math.round(lead.duration_seconds / 60)} 分钟` : '',
        '事件日期、机位、画面和授权未核实',
      ].filter(Boolean).join(' · ');
    if (checkedAt) metadata.title = `检索时间：${checkedAt}`;
    item.append(metadata);
    $eventDiscovery.append(item);
  }
  if (leads.length === 0) {
    $eventDiscovery.textContent = '本次检索没有可显示的候选。';
  }
}

function renderPublishedEvents(payload) {
  const publications = Array.isArray(payload.publications) ? payload.publications : [];
  $publishedEvents.replaceChildren();
  const clipCount = publications.reduce(
    (count, publication) => count + (Array.isArray(publication.clips) ? publication.clips.length : 0),
    0,
  );
  $publishedEventsStatus.textContent = `${publications.length} 个事件版本 · ${clipCount} 支短片`;
  for (const publication of publications) {
    const event = document.createElement('article');
    event.className = 'published-event';
    const heading = document.createElement('div');
    heading.className = 'published-event-heading';
    const title = document.createElement('h3');
    title.textContent = publication.identity?.title || publication.event_id;
    const eventDetails = document.createElement('p');
    eventDetails.className = 'meta';
    eventDetails.textContent = [
      `Event ID ${publication.event_id}`,
      `事件日期 ${eventText(publication.identity?.event_date, '未核实')}`,
      `同事件 ${eventText(publication.source_match_review_status)}`,
      `来源画面 ${eventText(publication.source_frame_review_status)}`,
      `字幕 ${eventText(publication.caption_review_status)}`,
      `翻译 ${eventText(publication.translation_status)}`,
    ].join(' · ');
    const source = document.createElement('p');
    source.className = 'published-source';
    source.append(
      document.createTextNode('制作来源：'),
      eventLink(publication.source_url, publication.source_url || '来源未登记'),
      document.createTextNode(' · 官方事件锚：'),
      eventLink(publication.official_video_url, publication.official_video_url || '锚点未登记'),
    );
    heading.append(title, eventDetails, source);
    const grid = document.createElement('div');
    grid.className = 'published-clip-grid';
    for (const clip of publication.clips || []) {
      const card = document.createElement('article');
      card.className = 'published-clip';
      const player = document.createElement('video');
      player.controls = true;
      player.preload = 'metadata';
      player.playsInline = true;
      const source = document.createElement('source');
      source.src = safeHttpUrl(clip.video_url) || '';
      source.type = 'video/mp4';
      player.append(source);
      const clipTitle = document.createElement('h4');
      clipTitle.textContent = `${clip.title || clip.highlight_id} · ${clip.style || 'Variant'}`;
      const clipMeta = document.createElement('p');
      clipMeta.className = 'meta';
      const start = Number(clip.source_start);
      const end = Number(clip.source_end);
      clipMeta.textContent = [
        Number.isFinite(start) && Number.isFinite(end) ? `原片 ${formatTime(start)}–${formatTime(end)}` : '',
        clip.resolution || '',
        Number.isFinite(clip.duration_seconds) ? `${clip.duration_seconds}s` : '',
      ].filter(Boolean).join(' · ');
      const links = document.createElement('p');
      links.className = 'published-clip-links';
      const videoLink = eventLink(clip.video_url, '视频 / 下载 MP4');
      videoLink.removeAttribute('target');
      videoLink.removeAttribute('rel');
      links.append(videoLink);
      if (clip.subtitle_url) {
        const subtitleLink = eventLink(clip.subtitle_url, '下载中英 SRT');
        subtitleLink.removeAttribute('target');
        subtitleLink.removeAttribute('rel');
        links.append(subtitleLink);
      }
      const reason = document.createElement('p');
      reason.className = 'published-clip-reason';
      reason.textContent = clip.reason ? `入选理由：${clip.reason}` : '';
      card.append(player, clipTitle, clipMeta, reason, links);
      grid.append(card);
    }
    event.append(heading, grid);
    $publishedEvents.append(event);
  }
  if (publications.length === 0) {
    $publishedEvents.textContent = '暂无已通过发布复核的短片。';
  }
}

async function loadEvents() {
  try {
    const response = await fetch('outputs/event-catalog.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Event source catalog is unavailable');
    renderCatalog(await response.json());
  } catch (error) {
    console.error(error);
    $eventCatalog.textContent = '事件来源目录暂不可用。';
  }

  const discoverySets = [];
  const discoveryFailures = [];
  for (const [kind, path] of [
    ['video', 'outputs/whitehouse-discovery.json'],
    ['article', 'outputs/gdelt-discovery.json'],
  ]) {
    try {
      const response = await fetch(path, { cache: 'no-store' });
      if (!response.ok) {
        discoveryFailures.push(`${kind} HTTP ${response.status}`);
        continue;
      }
      discoverySets.push({ kind, payload: await response.json() });
    } catch (error) {
      console.error(`Failed to load ${kind} discovery data`, error);
      discoveryFailures.push(kind);
    }
  }
  if (discoverySets.length) {
    renderDiscovery(discoverySets);
    if (discoveryFailures.length) {
      $eventDiscoveryStatus.textContent += ` · 未载入：${discoveryFailures.join(', ')}`;
    }
  } else {
    $eventDiscoveryStatus.textContent = discoveryFailures.length
      ? `检索结果暂不可用：${discoveryFailures.join(', ')}`
      : '尚无云端检索记录';
    $eventDiscovery.textContent = '视频与新闻文章只进入未分配线索；须人工核实事件后才归入相应事件组。';
  }

  try {
    const response = await fetch('outputs/published-events.json', { cache: 'no-store' });
    if (!response.ok) {
      $publishedEventsStatus.textContent = '暂无已发布版本';
      $publishedEvents.textContent = '生成过程与公开发布分开；作品须在云端产出后再通过来源、字幕、翻译及复用权利复核。';
      return;
    }
    renderPublishedEvents(await response.json());
  } catch (error) {
    console.error(error);
    $publishedEventsStatus.textContent = '已发布作品暂不可用';
  }
}

loadEvents();
