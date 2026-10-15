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

  function rank(sources) {
    return sources
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
      .slice(0, 10)
      .map(({ source }) => source);
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

  global.MainVideoRanking = Object.freeze({ rank, statusLabel, overlayLabel });
}(globalThis));
