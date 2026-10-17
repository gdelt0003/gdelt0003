const manifestUrl = new URL('../../outputs/pvXbHQrIvTw/comparison.json', document.baseURI);
const $eventTitle = document.getElementById('event-title');
const $eventSubtitle = document.getElementById('event-subtitle');
const $sourceLink = document.getElementById('source-link');
const $mediaStatus = document.getElementById('pvX-media-status');
const $pathwayGrid = document.getElementById('pathwayGrid');
const $comparisonRows = document.getElementById('comparisonRows');

function present(value) {
  return value === null || value === undefined || value === '' ? '未测 / 未提供' : String(value);
}

function safeHttpUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value, document.baseURI);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function appendLink(parent, label, value) {
  const url = safeHttpUrl(value);
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  link.textContent = label;
  link.rel = 'noreferrer';
  link.target = '_blank';
  parent.append(link);
}

function pathwayStatus(status) {
  const labels = {
    executed_unverified: '已运行 · 草稿未通过人工核验',
    caption_artifacts_reused_unverified: '复用既有字幕 · 未在本次重跑',
    proposed_not_runner_validated: '提案中 · 未合并/未完成 hosted-runner 验证',
    research_only_not_run: '研究候选 · 未运行',
    blocked_not_run: '受阻 · 未运行',
    observed_no_media_evidence: '观察到路线 · 无处理该媒体的证据',
    implemented_and_deployed: '工程实现已合并并部署',
  };
  return labels[status] || '状态未记录';
}

function renderPathway(pathway) {
  const card = document.createElement('article');
  card.className = 'pathway-card';
  card.dataset.kind = pathway.kind || 'unknown';

  const type = document.createElement('p');
  type.className = 'eyebrow';
  const kinds = {
    copilot_engineering: 'MICROSOFT / GITHUB COPILOT · REPOSITORY ENGINEERING',
    microsoft_media: 'MICROSOFT · MEDIA PROCESSING',
    microsoft_frontier: 'MICROSOFT FRONTIER · OBSERVED ROUTE',
    open_source_media: 'OPEN-SOURCE MEDIA TOOL',
  };
  type.textContent = kinds[pathway.kind] || 'MEDIA ROUTE';
  card.append(type);

  const title = document.createElement('h3');
  title.textContent = pathway.label || '未命名路线';
  card.append(title);

  const status = document.createElement('p');
  status.className = 'pathway-status';
  status.textContent = pathwayStatus(pathway.status);
  card.append(status);

  const summary = document.createElement('p');
  summary.textContent = pathway.summary || '没有附带可核验的路线说明。';
  card.append(summary);

  if (pathway.source_commit) {
    const commit = document.createElement('p');
    commit.className = 'meta pathway-commit';
    commit.textContent = `固定上游 commit：${pathway.source_commit}`;
    card.append(commit);
  }

  if (pathway.license_label) {
    const license = document.createElement('p');
    license.className = 'meta pathway-license';
    license.textContent = `上游仓库许可证：${pathway.license_label}`;
    card.append(license);
  } else if (pathway.license_note) {
    const license = document.createElement('p');
    license.className = 'meta pathway-license';
    license.textContent = pathway.license_note;
    card.append(license);
  }

  if (safeHttpUrl(pathway.video_url)) {
    const warning = document.createElement('p');
    warning.className = 'preview-media-label';
    warning.textContent = '机器生成 · 未经人工核验 · 非最终版本';
    card.append(warning);
    const player = document.createElement('video');
    player.controls = true;
    player.preload = 'metadata';
    player.playsInline = true;
    player.src = safeHttpUrl(pathway.video_url);
    player.setAttribute('aria-label', 'pvXbHQrIvTw SmartSub 未核验草稿预览');
    card.append(player);
  }

  const links = document.createElement('p');
  links.className = 'pathway-links';
  appendLink(links, '上游开源仓库', pathway.repository_url);
  appendLink(links, '翻译模型来源', pathway.translation_source_url);
  appendLink(links, '预览 Release', pathway.artifact_url);
  appendLink(links, '实际运行记录', pathway.workflow_url);
  appendLink(links, '相关 PR / 证据', pathway.evidence_url);
  appendLink(links, 'Pages 部署运行', pathway.deployment_url);
  appendLink(links, '上游来源说明', pathway.source_hub_url);
  appendLink(links, '许可证来源', pathway.license_url);
  for (const deliverable of pathway.deliverables || []) {
    appendLink(links, deliverable.label, deliverable.url);
  }
  if (links.children.length) card.append(links);
  return card;
}

function renderComparisonRows() {
  const rows = [
    [
      '工作类型',
      '五条媒体路线；仅 SmartSub 3.9.0 有本事件的公开草稿预览',
      'Copilot coding-agent：仓库工程、runner 集成、测试与 Pages 发布',
    ],
    [
      '媒体处理工具',
      'SmartSub 3.9.0 实际处理/渲染视频；字幕模型与 renderer 分开归属',
      'coding-agent 未渲染此视频',
    ],
    [
      '未运行路线',
      'Copilot/GPT-6、VideoCaptioner、ytb2bili、Frontier 状态逐卡披露',
      '未运行或无媒体处理证据不构成质量结果',
    ],
    [
      '质量与性能',
      '源音/ASR、翻译、阅读速度和完整画面未验证；比较未测量',
      '未提供或未知的耗时、分数及指标保持未知',
    ],
    [
      '工程交付证据',
      'SmartSub 上游依赖保持来源归属；不复制或冒领上游代码',
      'PR #21、#23、#25 与既有 Pages 部署证据',
    ],
  ];

  $comparisonRows.replaceChildren();
  for (const row of rows) {
    const tr = document.createElement('tr');
    row.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      if (index === 0) cell.scope = 'row';
      cell.textContent = value;
      tr.append(cell);
    });
    $comparisonRows.append(tr);
  }
}

function renderComparison(manifest) {
  const event = manifest.event || {};
  $eventTitle.textContent = event.title || '双语字幕方案对照';
  $eventSubtitle.textContent = [
    `事件日期（来源标题）：${present(event.event_date)}`,
    `地点：${present(event.location)}`,
    `本地时间：${present(event.event_time_local)}`,
    `来源匹配：${present(event.source_match_status)}`,
    `复用权利：${present(event.reuse_rights_status)}`,
  ].join(' · ');
  const sourceUrl = safeHttpUrl(event.source_url);
  if (sourceUrl) $sourceLink.href = sourceUrl;

  const pathways = manifest.pathways || [];
  const copilot = manifest.copilot_engineering;
  $pathwayGrid.replaceChildren(
    ...pathways.map(renderPathway),
    ...(copilot ? [renderPathway({ ...copilot, kind: 'copilot_engineering' })] : []),
  );

  const previewAvailable = manifest.smartsub_preview?.status === 'public_unverified_preview';
  $mediaStatus.textContent = previewAvailable
    ? '发布状态：仅公开机器生成、未经人工核验的草稿预览；正式发布门槛仍受阻。'
    : '发布状态：视频与字幕尚未公开。';
  renderComparisonRows();
}

async function loadComparison() {
  try {
    const response = await fetch(manifestUrl, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Comparison manifest HTTP ${response.status}`);
    renderComparison(await response.json());
  } catch (error) {
    console.error('Unable to load the subtitle comparison manifest', error);
    $eventSubtitle.textContent = '对照清单暂不可用；不展示推断或占位成片。';
  }
}

loadComparison();
