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
  type.textContent = pathway.kind === 'copilot_engineering'
    ? 'MICROSOFT / GITHUB COPILOT · ENGINEERING'
    : 'OPEN-SOURCE MEDIA TOOL / MODEL';
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
      '媒体处理：识别/翻译输入、字幕排版、硬字幕渲染',
      '仓库工程：runner 集成、来源/产物登记、测试与 Pages 部署',
    ],
    [
      '已交付证据',
      'SmartSub run 与公开预览；字幕来源及质量状态随路线卡列明',
      'PR #21、#23、#25 与成功的 Pages deployment run',
    ],
    [
      '开源代码归属',
      '上游工具保留仓库、固定版本与来源链接；不把上游源码称为本仓库原创',
      '本仓库的编排、适配和页面更改按项目提交记录归属',
    ],
    [
      '质量分数',
      '当前预览未完成人工核验；没有同任务的多路盲测分数',
      'Coding-agent 工程交付不是 ASR/翻译模型结果，不能套用媒体质量分数',
    ],
    [
      'GPT-6 归属',
      '媒体 provenance 记录 SmartSub 与字幕模型；未将成片标记为 GPT-6 输出',
      'Copilot 会话模型未写入该媒体 provenance；不据此否认 agent 可调用 GPT-6',
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
