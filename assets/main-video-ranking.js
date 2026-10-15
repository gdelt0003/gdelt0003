(function registerMainVideoRanking(global) {
  function numericValue(source, key) {
    const value = source?.[key];
    return Number.isFinite(value) && value >= 0 ? value : -1;
  }

  function resolutionPixels(value) {
    if (typeof value !== 'string') return -1;
    const match = /(\d{3,5})\s*[x×]\s*(\d{3,5})/i.exec(value);
    if (!match) return -1;
    return Number(match[1]) * Number(match[2]);
  }

  function statusRank(value) {
    return ({ confirmed: 2, lead: 1, unverified: 0 })[String(value || '').toLowerCase()] ?? -1;
  }

  function overlayRank(value) {
    return ({
      clear_verified: 3,
      possible_overlay: 2,
      overlay_present: 1,
      unassessed: 0,
    })[String(value || 'unassessed').toLowerCase()] ?? 0;
  }

  function categoryName(value) {
    const raw = String(value || '').trim().toLowerCase();
    if (!raw) return 'other';
    if (['video', 'videos', 'youtube', 'tv', 'clip', 'stream', 'livestream'].includes(raw)) return 'video';
    if (['news', 'newsroom', 'news_article', 'press', 'article', 'broadcast', 'media'].includes(raw)) return 'news';
    if (['social', 'tweet', 'x', 'twitter', 'truthsocial', 'facebook', 'instagram', 'tiktok', 'threads', 'mastodon'].includes(raw)) return 'social';
    if (raw.includes('social')) return 'social';
    if (raw.includes('news')) return 'news';
    if (raw.includes('video')) return 'video';
    return 'other';
  }

  function inferCategory(source) {
    if (!source || typeof source !== 'object') return 'other';
    const direct = source.category || source.type || source.source_type || source.kind || source.source_kind;
    if (direct) return categoryName(direct);

    const platform = String(source.hosting_platform || source.platform || '').toLowerCase();
    if (['youtube', 'vimeo', 'rumble', 'bitchute', 'facebook', 'x', 'twitter', 'tiktok', 'instagram', 'truthsocial'].includes(platform)) {
      return platform === 'youtube' ? 'video' : (platform === 'truthsocial' || platform === 'x' || platform === 'twitter' || platform === 'instagram' || platform === 'facebook' || platform === 'tiktok' ? 'social' : 'video');
    }

    const url = String(source.url || '');
    if (/(x\.com|twitter\.com|truthsocial\.com|instagram\.com|facebook\.com|tiktok\.com|threads\.net|mastodon)/.test(url)) return 'social';
    if (/(apnews|reuters|cnn|bbc|cbs|npr|foxnews|msnbc|nbc|c-span|abc|axios|politico|washingtonpost|nytimes|wsj|aljazeera)/i.test(url)) return 'news';
    return 'video';
  }

  function rank(sources) {
    return (Array.isArray(sources) ? sources : [])
      .map((source, index) => ({ source, index }))
      .sort((left, right) => {
        const a = left.source;
        const b = right.source;
        const criteria = [
          [Number(Boolean(b.event_anchor)), Number(Boolean(a.event_anchor))],
          [statusRank(b.classification), statusRank(a.classification)],
          [overlayRank(b.overlay_status), overlayRank(a.overlay_status)],
          [resolutionPixels(b.max_resolution), resolutionPixels(a.max_resolution)],
          [numericValue(b, 'duration_seconds'), numericValue(a, 'duration_seconds')],
          [numericValue(b, 'view_count'), numericValue(a, 'view_count')],
        ];
        for (const [leftValue, rightValue] of criteria) {
          if (leftValue !== rightValue) return leftValue - rightValue;
        }
        return left.index - right.index;
      })
      .map(({ source }) => source);
  }

  function groupByCategory(sources) {
    const ranked = rank(sources);
    const groups = new Map();
    for (const source of ranked) {
      const category = inferCategory(source);
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(source);
    }

    const order = ['video', 'news', 'social', 'other'];
    const categories = [];
    for (const category of order) {
      if (category === 'other' && !groups.has(category)) continue;
      const items = groups.get(category) || [];
      categories.push({
        category,
        label: category === 'video' ? '视频' : category === 'news' ? '新闻/媒体' : category === 'social' ? '社交/平台' : '其他',
        total: items.length,
        confirmedCount: items.filter((source) => String(source.classification || '').toLowerCase() === 'confirmed').length,
        sources: items,
      });
    }
    for (const [category, items] of groups.entries()) {
      if (!order.includes(category)) {
        categories.push({
          category,
          label: '其他',
          total: items.length,
          confirmedCount: items.filter((source) => String(source.classification || '').toLowerCase() === 'confirmed').length,
          sources: items,
        });
      }
    }
    return categories;
  }

  function evidenceScore(source) {
    const entry = source || {};
    let total = 0;
    const checks = [];
    const isAssessedValue = (value) => (
      typeof value === 'string'
      && value.trim() !== ''
      && !/(unassessed|unverified|unknown|not[_ -]?verified|未核验|未验证|未核实|未知)/i.test(value.trim())
    );

    function addCheck(label, passes) {
      checks.push({ label, passes });
      if (passes) total += 1;
    }

    addCheck('direct_url', !!(typeof entry.url === 'string' && entry.url.trim()));
    addCheck('title_or_publisher', !!((entry.title && entry.title.trim()) || (entry.publisher && entry.publisher.trim())));
    addCheck('publish_time', !!(entry.upload_date || entry.publish_date || entry.event_time));
    addCheck('resolution', !!(entry.max_resolution || entry.resolution));
    addCheck('duration', Number.isFinite(entry.duration_seconds) && entry.duration_seconds >= 0);
    addCheck(
      'overlay_review',
      ['clear_verified', 'possible_overlay', 'overlay_present'].includes(String(entry.overlay_status || '').toLowerCase())
        || isAssessedValue(entry.overlay_assessment),
    );
    addCheck(
      'caption_review',
      (Array.isArray(entry.captions) && entry.captions.length > 0)
        || isAssessedValue(entry.caption_provenance?.verification),
    );
    addCheck('provenance_notes', !!(entry.notes || entry.checked_fields || entry.checked_with));

    const score = Math.round((total / checks.length) * 100);
    return {
      score,
      checks,
      basis: checks
        .filter((item) => item.passes)
        .map((item) => item.label)
        .join(', '),
      unknowns: checks
        .filter((item) => !item.passes)
        .map((item) => item.label),
    };
  }

  function scoreBasisLabel(source) {
    const info = evidenceScore(source);
    const labelMap = {
      direct_url: '直链 URL',
      title_or_publisher: '标题/发布方',
      publish_time: '时间信息',
      resolution: '分辨率',
      duration: '时长',
      overlay_review: '画面/横幅评估',
      caption_review: '字幕/字幕轨记录',
      provenance_notes: '核验说明或证据笔记',
    };
    const known = (info.basis || '')
      .split(', ')
      .filter(Boolean)
      .map((key) => labelMap[key] || key);
    const missing = info.unknowns.map((key) => labelMap[key] || key);
    return `${known.join('、') || '无已记录项'}；unknown/unreviewed: ${missing.join('、') || '无'}`;
  }

  function scoreDisplayLabel(source) {
    const { score } = evidenceScore(source);
    return `${score}/100`;
  }

  function statusLabel(value) {
    return ({
      confirmed: '事件匹配已确认',
      lead: '事件相关候选',
      unverified: '事件匹配未核实',
    })[String(value || '').toLowerCase()] || '事件匹配状态未知';
  }

  function overlayLabel(value) {
    return ({
      clear_verified: '已复核：未见内嵌横幅/标志',
      possible_overlay: '可能有内嵌横幅/标志（未确认）',
      overlay_present: '已观察到内嵌横幅/标志',
      unassessed: '未核验',
    })[String(value || 'unassessed').toLowerCase()] || '未核验';
  }

  function userSubjectiveScore(source) {
    const value = source?.caption_provenance?.user_given_reference_score;
    if (typeof value === 'number' && Number.isFinite(value)) {
      return { value, note: source?.caption_provenance?.user_score_note || '用户提供的参考分，非证据覆盖分' };
    }
    return null;
  }

  global.MainVideoRanking = Object.freeze({
    rank,
    groupByCategory,
    statusLabel,
    overlayLabel,
    inferCategory,
    categoryName,
    evidenceScore,
    scoreBasisLabel,
    scoreDisplayLabel,
    userSubjectiveScore,
  });
}(globalThis));
