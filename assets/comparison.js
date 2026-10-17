const manifestUrl = new URL('../../outputs/pvXbHQrIvTw/comparison.json', document.baseURI);
const $comparisonRows = document.getElementById('comparison-rows');
const $eventTitle = document.getElementById('event-title');
const $eventSubtitle = document.getElementById('event-subtitle');
const $sourceLink = document.getElementById('source-link');
const $mediaStatus = document.getElementById('pvX-media-status');

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

function setLink(url, label) {
  const safeUrl = safeHttpUrl(url);
  if (!safeUrl) {
    const unavailable = document.createElement('span');
    unavailable.className = 'meta';
    unavailable.textContent = `${label}：尚未生成或链接无效`;
    return unavailable;
  }
  const link = document.createElement('a');
  link.href = safeUrl;
  link.textContent = label;
  link.rel = 'noreferrer';
  link.target = '_blank';
  return link;
}

function renderAudit(container, audit) {
  const title = document.createElement('h3');
  title.textContent = '处理审计';
  container.append(title);
  const list = document.createElement('ul');
  const steps = ['source_validation', 'asr', 'translation', 'subtitle_export', 'video_burn', 'quality_review'];
  for (const step of steps) {
    const record = Array.isArray(audit) ? audit.find((item) => item?.operation === step) : null;
    const item = document.createElement('li');
    item.textContent = `${step}: ${record?.status || 'not_run'}${record?.model ? ` · ${record.model}` : ''}`;
    list.append(item);
  }
  container.append(list);
}

function renderVariant(variant, elementId) {
  const root = document.querySelector(`#${elementId} .variant-content`);
  root.replaceChildren();
  const state = document.createElement('p');
  state.className = 'comparison-state';
  state.dataset.state = variant.status || 'not_run';
  state.textContent = variant.status === 'agent_route_observed_media_pipeline_not_run'
    ? '已观察到 Copilot coding agent 的产品内模型路由证据；没有证据表明该 agent 或 GPT-6 处理了这份媒体。'
    : variant.status === 'blocked_model_unavailable'
      ? '未运行：尚无经确认的应用侧媒体模型处理配置；未用其他模型冒充。'
    : variant.status === 'preview_unverified'
      ? '公开机器生成草稿预览，未经人工核验；源音/ASR、翻译、阅读速度和全片画面检查仍未通过或未验证。'
    : variant.status === 'complete'
      ? '已生成；字幕与画面审校状态见下方记录。'
      : '未运行：等待具备授权的云端处理与复核。';
  root.append(state);

  const videoUrl = safeHttpUrl(variant.video_url);
  if (videoUrl) {
    const warning = document.createElement('p');
    warning.className = 'preview-media-label';
    warning.textContent = '机器生成 · 未经人工核验 · 非最终版本';
    root.append(warning);
    const video = document.createElement('video');
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;
    video.setAttribute('aria-label', '机器生成、未经人工核验的 pvXbHQrIvTw 双语字幕视频草稿');
    video.src = videoUrl;
    root.append(video);
  }

  const details = document.createElement('dl');
  for (const [label, value] of [
    ['ASR 模型', variant.models?.asr],
    ['翻译模型', variant.models?.translation],
    ['渲染流程', variant.render],
  ]) {
    const term = document.createElement('dt');
    term.textContent = label;
    const definition = document.createElement('dd');
    definition.textContent = present(value);
    details.append(term, definition);
  }
  root.append(details);

  const transcriptTitle = document.createElement('h3');
  transcriptTitle.textContent = '识别与翻译文本';
  root.append(transcriptTitle);
  for (const [label, text] of [['English', variant.transcript?.english], ['简体中文', variant.transcript?.chinese]]) {
    const heading = document.createElement('p');
    heading.className = 'meta';
    heading.textContent = label;
    root.append(heading);
    const output = document.createElement('pre');
    output.textContent = text || '尚无生成文本';
    root.append(output);
  }

  const links = document.createElement('p');
  links.className = 'comparison-links';
  const draftPrefix = variant.status === 'preview_unverified'
    ? '机器生成未核验草稿 · '
    : '';
  links.append(
    setLink(variant.subtitles?.english, `${draftPrefix}English SRT`),
    setLink(variant.subtitles?.chinese, `${draftPrefix}中文 SRT`),
    setLink(variant.subtitles?.bilingual, `${draftPrefix}中英双语 SRT`),
  );
  root.append(links);
  renderAudit(root, variant.audit);

  const checks = document.createElement('h3');
  checks.textContent = '质量检查';
  root.append(checks);
  const quality = document.createElement('ul');
  for (const [name, result] of Object.entries(variant.quality_checks || {})) {
    const item = document.createElement('li');
    item.textContent = `${name}: ${present(result)}`;
    quality.append(item);
  }
  root.append(quality);
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

  const byId = Object.fromEntries((manifest.variants || []).map((variant) => [variant.id, variant]));
  renderVariant(byId['open-source-baseline'] || {}, 'variant-open-source');
  renderVariant(byId['microsoft-copilot-gpt6'] || {}, 'variant-microsoft');
  renderVariant(byId['videocaptioner-japanese'] || {}, 'variant-videocaptioner');
  renderVariant(byId['ytb2bili-video-pipeline'] || {}, 'variant-ytb2bili');
  renderVariant(byId['microsoft-frontier-stack'] || {}, 'variant-microsoft-frontier');
  const previewAvailable = manifest.smartsub_preview?.status === 'public_unverified_preview';
  $mediaStatus.textContent = previewAvailable
    ? '发布状态：仅公开机器生成、未经人工核验的草稿预览；正式发布门槛仍受阻。'
    : '发布状态：视频与字幕尚未公开。';

  const metrics = [
    ['本机文件大小（元数据）', 'local_file_size_bytes', 'local_file_size_bytes', '云端需核对同一输入的字节数与 SHA-256'],
    ['runner 实际处理输入大小', 'processed_input_size_bytes', 'processed_input_size_bytes', '两版均由云端审计记录确认'],
    ['输入 SHA-256', 'input_sha256', 'input_sha256', '两版哈希完全一致'],
    ['视频时长', 'duration_seconds', 'duration_seconds', '同一原片时长'],
    ['成片分辨率', 'resolution', 'resolution', '读取成片实际流信息'],
    ['处理耗时（秒）', 'processing_seconds', 'processing_seconds', '相同云端 runner 资源'],
    ['实际成本（美元）', 'cost_usd', 'cost_usd', '记录模型与云端账单，不估算'],
    ['WER（英语）', 'wer', 'wer', '同一人工转录参考稿'],
    ['翻译盲评', 'translation_score', 'translation_score', '同样本、盲评并报告样本数'],
    ['字幕 cue 同步误差（毫秒）', 'cue_sync_error_ms', 'cue_sync_error_ms', '对照实际音频并报告中位数/P90'],
  ];
  $comparisonRows.replaceChildren();
  for (const [label, openKey, microsoftKey, condition] of metrics) {
    const row = document.createElement('tr');
    const openSource = byId['open-source-baseline']?.metrics || {};
    const microsoft = byId['microsoft-copilot-gpt6']?.metrics || {};
    const eventMetric = openKey === 'local_file_size_bytes';
    const firstValue = eventMetric ? event[openKey] : openSource[openKey];
    const secondValue = eventMetric ? event[microsoftKey] : microsoft[microsoftKey];
    for (const value of [label, firstValue, secondValue, condition]) {
      const cell = document.createElement(value === label ? 'th' : 'td');
      if (value === label) cell.scope = 'row';
      cell.textContent = value === label ? value : present(value);
      row.append(cell);
    }
    $comparisonRows.append(row);
  }
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
