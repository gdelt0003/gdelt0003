const $officialVideoLeads = document.getElementById('officialVideoLeads');
const $officialVideoLeadsStatus = document.getElementById('officialVideoLeadsStatus');
const visibleLeadLimit = 10;

function officialVideoUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value.trim(), document.baseURI);
    if (
      url.protocol !== 'https:'
      || !['youtube.com', 'www.youtube.com'].includes(url.hostname)
      || url.pathname !== '/watch'
      || !url.searchParams.get('v')
    ) return null;
    return url.href;
  } catch {
    return null;
  }
}

function leadDate(lead, checkedAt) {
  const uploadDate = typeof lead.upload_date_metadata === 'string'
    ? lead.upload_date_metadata
    : '';
  if (/^\d{8}$/.test(uploadDate)) {
    return `上传日期元数据 ${uploadDate.slice(0, 4)}-${uploadDate.slice(4, 6)}-${uploadDate.slice(6, 8)}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(uploadDate)) {
    return `上传日期元数据 ${uploadDate}`;
  }
  if (Number.isFinite(lead.published_timestamp_unix) && lead.published_timestamp_unix > 0) {
    return `上传时间戳 ${new Date(lead.published_timestamp_unix * 1000).toISOString().slice(0, 10)}`;
  }
  const snapshotDate = typeof checkedAt === 'string' ? checkedAt.slice(0, 10) : '';
  return `上传日期未知 · 目录快照 ${/^\d{4}-\d{2}-\d{2}$/.test(snapshotDate) ? `${snapshotDate} UTC` : '日期未知'}`;
}

function renderOfficialVideoLeads(payload) {
  const leads = Array.isArray(payload?.leads)
    ? payload.leads.filter((lead) => officialVideoUrl(lead?.url))
    : [];
  const visibleLeads = leads.slice(0, visibleLeadLimit);

  $officialVideoLeads.replaceChildren();
  $officialVideoLeadsStatus.textContent = leads.length
    ? `显示 ${visibleLeads.length} / ${leads.length} 条官方频道元数据线索`
    : '暂无可显示的白宫频道视频线索';

  for (const lead of visibleLeads) {
    const card = document.createElement('article');
    card.className = 'official-video-lead';

    const title = document.createElement('h3');
    const source = document.createElement('a');
    source.href = officialVideoUrl(lead.url);
    source.target = '_blank';
    source.rel = 'noreferrer';
    source.textContent = lead.title || lead.video_id || '未命名频道条目';
    title.append(source);

    const metadata = document.createElement('p');
    metadata.className = 'meta';
    metadata.textContent = [
      lead.publisher || '发布方未提供',
      leadDate(lead, payload.checked_at_utc),
      Number.isFinite(lead.duration_seconds) && lead.duration_seconds >= 0
        ? `${Math.floor(lead.duration_seconds / 60)} 分 ${lead.duration_seconds % 60} 秒`
        : '',
    ].filter(Boolean).join(' · ');

    const status = document.createElement('p');
    status.className = 'official-video-lead-status';
    status.textContent = '元数据线索 · 事件、内容与复用权利未核实';

    card.append(title, metadata, status);
    $officialVideoLeads.append(card);
  }

  if (!visibleLeads.length) {
    $officialVideoLeads.textContent = '当前快照没有可显示的有效视频条目；这不代表频道没有其他视频。';
  }
}

async function loadOfficialVideoLeads() {
  try {
    const response = await fetch('outputs/whitehouse-discovery.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`White House discovery HTTP ${response.status}`);
    renderOfficialVideoLeads(await response.json());
  } catch (error) {
    console.error('Unable to load White House channel metadata leads', error);
    $officialVideoLeadsStatus.textContent = '白宫频道元数据线索暂不可用';
    $officialVideoLeads.textContent = '当前无法读取本地发现快照；请稍后重试或打开白宫官方频道。';
  }
}

loadOfficialVideoLeads();
