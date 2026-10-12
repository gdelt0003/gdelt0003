(() => {
  const API = 'data/catalog.json';
  const VIDEO_PAGE_SIZE = 24;
  const YOUTUBE_HOSTS = new Set([
    'youtube.com',
    'www.youtube.com',
    'm.youtube.com',
    'music.youtube.com',
    'youtu.be',
    'www.youtu.be',
  ]);
  const elements = {
    grid: document.getElementById('videoGrid'),
    status: document.getElementById('status'),
    refresh: document.getElementById('refreshBtn'),
    search: document.getElementById('searchInput'),
    summary: document.getElementById('resultSummary'),
    pagination: document.getElementById('pagination'),
    sourceDetails: document.getElementById('sourceDetails'),
    sourceList: document.getElementById('sourceList'),
  };
  let videos = [];
  let sourceStatuses = [];
  let shorts = [];
  let generatedAt = '';
  let page = 1;

  function safeUrl(value, allowedHosts) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && allowedHosts.some(host => url.hostname === host || url.hostname.endsWith(`.${host}`))
        ? url.href
        : '';
    } catch {
      return '';
    }
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function safeRunUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && url.hostname === 'github.com' &&
        /^\/[^/]+\/[^/]+\/actions\/runs\/\d+\/?$/.test(url.pathname)
        ? url.href
        : '';
    } catch {
      return '';
    }
  }

  function videoIdFromUrl(value) {
    try {
      const url = new URL(value);
      if (!YOUTUBE_HOSTS.has(url.hostname)) return '';
      if (url.hostname === 'youtu.be' || url.hostname === 'www.youtu.be') return url.pathname.slice(1).split('/')[0];
      if (url.pathname === '/watch') return url.searchParams.get('v') || '';
      const match = url.pathname.match(/^\/(?:shorts|embed)\/([^/]+)/);
      return match ? match[1] : '';
    } catch {
      return '';
    }
  }

  function relatedShort(video) {
    return shorts.find(short => {
      const active = short.status === 'available' && Date.parse(short.expiresAt) > Date.now();
      const sameVideo = short.videoId && String(short.videoId) === String(video.id);
      const sameSource = short.sourceUrl && (
        short.sourceUrl === video.url ||
        videoIdFromUrl(short.sourceUrl) === String(video.id)
      );
      return active && (sameVideo || sameSource);
    });
  }

  function makeCard(video) {
    const card = createElement('article', 'video-card');
    const imageLink = createElement('a', 'thumbnail-link');
    const videoUrl = safeUrl(video.url, [...YOUTUBE_HOSTS]);
    if (videoUrl) {
      imageLink.href = videoUrl;
      imageLink.target = '_blank';
      imageLink.rel = 'noopener noreferrer';
      imageLink.setAttribute('aria-label', `Watch ${video.title || 'video'} on YouTube`);
    }
    const thumbnail = createElement('div', 'thumbnail');
    const imageUrl = safeUrl(video.thumbnail, ['ytimg.com', 'googleusercontent.com']);
    if (imageUrl) {
      const image = createElement('img');
      image.src = imageUrl;
      image.alt = '';
      image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer';
      thumbnail.append(image);
    } else {
      thumbnail.append(createElement('span', 'thumbnail-placeholder', '▶'));
    }
    const duration = video.duration || (Number.isFinite(video.durationSeconds) && video.durationSeconds > 0
      ? `${Math.floor(video.durationSeconds / 60)}:${String(video.durationSeconds % 60).padStart(2, '0')}`
      : '');
    if (duration) thumbnail.append(createElement('span', 'duration', duration));
    imageLink.append(thumbnail);

    const info = createElement('div', 'video-info');
    const title = createElement('h3', 'video-title');
    const titleLink = createElement('a', '', video.title || 'Untitled video');
    if (videoUrl) {
      titleLink.href = videoUrl;
      titleLink.target = '_blank';
      titleLink.rel = 'noopener noreferrer';
    }
    title.append(titleLink);
    info.append(title);
    info.append(createElement('p', 'video-author', video.author || 'YouTube'));

    const meta = createElement('div', 'video-meta');
    if (video.uploadDate) {
      const date = video.uploadDate.match(/^\d{8}$/)
        ? `${video.uploadDate.slice(0, 4)}-${video.uploadDate.slice(4, 6)}-${video.uploadDate.slice(6)}`
        : video.uploadDate;
      meta.append(createElement('span', '', date));
    }
    if (video.source) {
      const sourceUrl = safeUrl(video.source, [...YOUTUBE_HOSTS]);
      if (sourceUrl) {
        const source = createElement('a', 'source-link', 'Source');
        source.href = sourceUrl;
        source.target = '_blank';
        source.rel = 'noopener noreferrer';
        meta.append(source);
      }
    }
    info.append(meta);
    const short = relatedShort(video);
    if (short) {
      const derivative = createElement('section', `derived-short short-${short.status}`);
      derivative.append(createElement('p', 'derivative-label', 'Derived short candidate'));
      if (short.status === 'available') {
        derivative.append(createElement('p', 'derivative-title', short.clipTitle || 'Short edit'));
        const details = createElement(
          'p',
          'derivative-meta',
          `${short.durationSeconds}s · from ${short.startSeconds}s · ${short.captions || 'captions unavailable'} · ${short.selectionReason || ''}`,
        );
        derivative.append(details);
        const runLinkUrl = safeRunUrl(short.runUrl);
        if (runLinkUrl) {
          const artifactLink = createElement('a', 'short-download', `Open Actions run to download ${short.clipFile || 'short'} (14 days)`);
          artifactLink.href = runLinkUrl;
          artifactLink.target = '_blank';
          artifactLink.rel = 'noopener noreferrer';
          derivative.append(artifactLink);
        }
        derivative.append(createElement('p', 'derivative-note', short.reachDisclaimer || 'Editorial review recommended; reach is not guaranteed.'));
      } else {
        derivative.append(createElement('p', 'derivative-meta', `Generation failed: ${short.error || 'see the Actions run log'}`));
      }
      info.append(derivative);
    }
    card.append(imageLink, info);
    return card;
  }

  function renderPagination(totalPages) {
    elements.pagination.replaceChildren();
    if (totalPages <= 1) return;

    const previous = createElement('button', 'page-button', '← Previous');
    previous.type = 'button';
    previous.disabled = page <= 1;
    previous.addEventListener('click', () => {
      page -= 1;
      render();
      elements.grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    const indicator = createElement('span', 'page-indicator', `Page ${page} of ${totalPages}`);
    const next = createElement('button', 'page-button', 'Next →');
    next.type = 'button';
    next.disabled = page >= totalPages;
    next.addEventListener('click', () => {
      page += 1;
      render();
      elements.grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    elements.pagination.append(previous, indicator, next);
  }

  function render() {
    const query = elements.search.value.trim().toLocaleLowerCase();
    const filtered = videos.filter(video =>
      [video.title, video.author, video.source]
        .filter(Boolean)
        .some(value => String(value).toLocaleLowerCase().includes(query)),
    );
    const totalPages = Math.max(1, Math.ceil(filtered.length / VIDEO_PAGE_SIZE));
    page = Math.min(page, totalPages);
    const start = (page - 1) * VIDEO_PAGE_SIZE;
    const visible = filtered.slice(start, start + VIDEO_PAGE_SIZE);

    elements.grid.replaceChildren();
    if (!visible.length) {
      const message = videos.length
        ? 'No videos match your search. Try another title, channel, or playlist.'
        : sourceStatuses.some(source => source.status === 'success' || source.status === 'empty')
          ? 'No public videos were returned by the configured sources yet.'
          : 'No videos are available yet. Check the source update status below.';
      elements.grid.append(createElement('div', 'empty-state', message));
    } else {
      elements.grid.append(...visible.map(makeCard));
    }
    elements.summary.textContent = filtered.length
      ? `Showing ${start + 1}–${Math.min(start + VIDEO_PAGE_SIZE, filtered.length)} of ${filtered.length} videos`
      : `${filtered.length} videos`;
    renderPagination(totalPages);
  }

  function renderSourceStatuses() {
    elements.sourceList.replaceChildren();
    const failures = sourceStatuses.filter(source => source.status === 'failed');
    const empty = sourceStatuses.filter(source => source.status === 'empty');
    const successful = sourceStatuses.filter(source => source.status === 'success');
    elements.sourceDetails.hidden = sourceStatuses.length === 0;
    if (!sourceStatuses.length) {
      elements.status.textContent = 'No sources configured';
      return;
    }
    const updated = generatedAt ? new Date(generatedAt) : null;
    const updatedLabel = updated && !Number.isNaN(updated.getTime())
      ? ` · updated ${updated.toLocaleString()}`
      : '';
    elements.status.textContent =
      `${videos.length} videos · ${successful.length} sources updated · ` +
      `${empty.length} empty · ${failures.length} failed${updatedLabel}`;
    for (const source of sourceStatuses) {
      const row = createElement('li', `source-status source-${source.status}`);
      const label = source.status === 'success' ? `${source.videoCount} videos` :
        source.status === 'empty' ? 'No public videos' : `Failed: ${source.error || 'unknown error'}`;
      const link = safeUrl(source.url, [...YOUTUBE_HOSTS])
        ? createElement('a', '', source.url)
        : createElement('span', '', source.url || 'Unknown source');
      if (link.tagName === 'A') {
        link.href = safeUrl(source.url, [...YOUTUBE_HOSTS]);
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      row.append(link, createElement('span', 'source-result', label));
      elements.sourceList.append(row);
    }
  }

  async function loadCatalog() {
    elements.status.textContent = 'Loading catalog…';
    elements.refresh.disabled = true;
    try {
      const response = await fetch(`${API}?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
      const catalog = await response.json();
      if (!catalog || !Array.isArray(catalog.videos) || !Array.isArray(catalog.sources)) {
        throw new Error('Catalog has an unexpected format');
      }
      videos = catalog.videos;
      sourceStatuses = catalog.sources;
      shorts = Array.isArray(catalog.shorts) ? catalog.shorts : [];
      generatedAt = catalog.generatedAt || '';
      elements.search.value = new URLSearchParams(location.search).get('q') || '';
      page = 1;
      renderSourceStatuses();
      render();
    } catch (error) {
      videos = [];
      sourceStatuses = [];
      shorts = [];
      generatedAt = '';
      elements.grid.replaceChildren(createElement('div', 'empty-state', 'Unable to load the video catalog. Please try again later.'));
      elements.status.textContent = error instanceof Error ? error.message : 'Catalog load failed';
      elements.summary.textContent = '';
      elements.pagination.replaceChildren();
      elements.sourceDetails.hidden = true;
    } finally {
      elements.refresh.disabled = false;
    }
  }

  elements.search.addEventListener('input', () => {
    page = 1;
    const params = new URLSearchParams(location.search);
    if (elements.search.value.trim()) params.set('q', elements.search.value.trim());
    else params.delete('q');
    const query = params.toString();
    history.replaceState(null, '', query ? `?${query}` : location.pathname);
    render();
  });
  elements.refresh.addEventListener('click', loadCatalog);
  loadCatalog();
})();
