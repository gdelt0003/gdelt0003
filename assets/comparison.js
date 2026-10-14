const manifestPath = 'outputs/president-trump-gaggle-oct-13-2026/comparison.json';
const $identity = document.getElementById('eventIdentity');
const $variants = document.getElementById('comparisonVariants');
const $metrics = document.getElementById('comparisonMetrics');
const $releaseStatus = document.getElementById('comparisonReleaseStatus');

function label(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : '未验证 / 无数据';
}

function httpUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value, document.baseURI);
    return url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

function renderVariant(variant) {
  const card = document.createElement('article');
  card.className = 'comparison-variant';
  const heading = document.createElement('h3');
  heading.textContent = label(variant.name);
  const status = document.createElement('p');
  status.className = 'comparison-status';
  status.textContent = label(variant.status_label);
  const description = document.createElement('p');
  description.textContent = label(variant.description);
  const model = document.createElement('p');
  model.className = 'meta';
  model.textContent = `ASR：${label(variant.asr_model)} · 翻译：${label(variant.translation_model)}`;
  card.append(heading, status, description, model);
  for (const [key, linkLabel] of [['video_url', '观看刻录视频'], ['subtitle_url', '下载字幕'], ['audit_url', '查看处理审计']]) {
    const safe = httpUrl(variant.assets?.[key]);
    if (!safe) continue;
    const link = document.createElement('a');
    link.href = safe;
    link.rel = 'noreferrer';
    link.textContent = linkLabel;
    card.append(link);
  }
  return card;
}

function renderMetric(metric) {
  const row = document.createElement('tr');
  for (const value of [metric.label, metric.variants?.copilot?.display, metric.variants?.open_source?.display]) {
    const cell = document.createElement('td');
    cell.textContent = label(value);
    row.append(cell);
  }
  return row;
}

function renderCheck(check) {
  const item = document.createElement('li');
  item.textContent = `${label(check.label)}：${label(check.status)}`;
  const safe = httpUrl(check.evidence_url);
  if (safe) {
    const link = document.createElement('a');
    link.href = safe;
    link.rel = 'noreferrer';
    link.textContent = '证据';
    item.append(' ', link);
  }
  return item;
}

async function loadComparison() {
  try {
    const response = await fetch(manifestPath, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    $identity.textContent = [
      data.event?.title || '事件标题未核实',
      `事件日期：${label(data.event?.date_display)}`,
      `身份状态：${label(data.event?.identity_status)}`,
      `Event ID：${label(data.event?.event_id)}`,
    ].join(' · ');
    $variants.replaceChildren(...(data.variants || []).map(renderVariant));
    $metrics.replaceChildren(...(data.metrics || []).map(renderMetric));
    $releaseStatus.replaceChildren(...(data.release_checks || []).map(renderCheck));
  } catch (error) {
    console.error('Unable to load the event comparison manifest', error);
    $identity.textContent = '事件对照清单暂不可用。';
    $variants.textContent = '未载入任何处理结果；不会显示推测产物。';
  }
}

loadComparison();
