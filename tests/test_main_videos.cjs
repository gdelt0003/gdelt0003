const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.classList = {
      toggle: (name, enabled) => {
        const tokens = new Set(this.className.split(/\s+/).filter(Boolean));
        if (enabled) tokens.add(name);
        else tokens.delete(name);
        this.className = [...tokens].join(' ');
      },
    };
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener(name, callback) {
    this.listeners ||= {};
    this.listeners[name] = callback;
  }

  querySelectorAll(selector) {
    return selector === '[data-main-video-filter]'
      ? this.children.filter((child) => child.dataset.mainVideoFilter)
      : [];
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }
}

async function main() {
  const videos = new Element('div');
  const status = new Element('span');
  const filters = new Element('div');
  const sort = new Element('select');
  sort.value = 'newest';
  for (const filter of ['all', 'machine', 'other']) {
    const button = new Element('button');
    button.dataset.mainVideoFilter = filter;
    button.setAttribute('aria-pressed', String(filter === 'all'));
    button.className = filter === 'all' ? 'is-active' : '';
    filters.append(button);
  }
  const elements = new Map([
    ['mainVideos', videos],
    ['mainVideosStatus', status],
    ['mainVideosFilters', filters],
    ['mainVideosSort', sort],
  ]);
  const document = {
    baseURI: 'https://example.test/site/',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };
  const payload = {
    videos: [
      {
        id: 'rose-garden-lunch-2026-10-15-review',
        title: 'Rose Garden Lunch · 外部审查草稿',
        event_date: '2026-10-15',
        homepage_status: '外部审查草稿 · 五项复核声明已记录',
        video_url: 'https://cdn.example.test/rose-garden.mp4',
        source_details_url: 'events/rose-garden-lunch-2026-10-15/',
        source_url: 'https://source.example.test/rose-garden',
      },
      {
        id: 'older',
        title: 'Older event',
        event_date: '2026-10-06',
        homepage_status: '字幕待复核',
        video_url: 'https://cdn.example.test/older.mp4',
        source_details_url: 'events/older/sources.html',
        source_url: 'https://source.example.test/older',
      },
      {
        id: 'newer',
        title: 'Newer event',
        event_date: '2026-10-13',
        publisher: 'White House',
        resolution: '1920x1080',
        duration_seconds: 865,
        homepage_status: '机器生成预览 · 未经人工核验',
        video_url: 'https://cdn.example.test/newer.mp4',
        source_details_url: 'events/newer/sources.html',
        source_url: 'https://source.example.test/newer',
        provenance: { sources: [{ id: 'hidden-details' }] },
      },
      {
        id: 'unsafe',
        title: 'Unsafe video',
        event_date: '2026-10-14',
        video_url: 'javascript:alert(1)',
      },
    ],
  };
  const context = {
    document,
    URL,
    fetch: async () => ({ ok: true, json: async () => payload }),
    console,
  };

  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-videos.js'), 'utf8'),
    context,
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(videos.children.length, 3, 'render all safe main videos');
  assert.equal(status.textContent, '3 条主视频', 'count only playable catalog entries');
  assert.equal(
    videos.children[0].children[1].children[0].textContent,
    'Rose Garden Lunch · 外部审查草稿',
  );
  assert.equal(videos.children[1].children[1].children[0].textContent, 'Newer event');
  assert.equal(videos.children[2].children[1].children[0].textContent, 'Older event');
  assert.equal(
    videos.children[0].children[0].children[0].src,
    'https://cdn.example.test/rose-garden.mp4',
  );
  assert.equal(
    videos.children[1].children[0].children[0].src,
    'https://cdn.example.test/newer.mp4',
  );

  const newestContent = videos.children[1].children[1];
  assert.equal(newestContent.children.length, 4, 'homepage cards keep only concise details');
  assert.equal(newestContent.children[1].textContent, '2026-10-13 · White House · 1920x1080 · 14 分钟');
  assert.equal(newestContent.children[2].textContent, '机器生成预览 · 未经人工核验');
  assert.equal(
    newestContent.children[3].children.map((link) => link.textContent).join(', '),
    '来源视频, 视频源与视频本身可信度详情, 下载 MP4',
  );
  assert.ok(
    !newestContent.children.some((node) => node.className === 'main-video-sources'),
    'full provenance is not expanded on the homepage',
  );
  assert.equal(
    newestContent.children[3].children[1].href,
    'https://example.test/site/events/newer/sources.html',
    'homepage cards link to event-specific source details',
  );

  filters.listeners.click({ target: filters.children[1] });
  assert.equal(videos.children.length, 1, 'machine-generated filter should show one draft');
  assert.equal(status.textContent, '1 条主视频 · 筛选结果');
  assert.equal(filters.children[1].attributes['aria-pressed'], 'true');
  assert.ok(filters.children[1].className.includes('is-active'));

  filters.listeners.click({ target: filters.children[2] });
  assert.equal(videos.children.length, 2, 'other-versions filter should show the other items');
  assert.deepEqual(
    videos.children.map((card) => card.children[1].children[0].textContent),
    ['Rose Garden Lunch · 外部审查草稿', 'Older event'],
  );

  filters.listeners.click({ target: filters.children[0] });
  sort.value = 'oldest';
  sort.listeners.change();
  assert.deepEqual(
    videos.children.map((card) => card.children[1].children[0].textContent),
    ['Older event', 'Newer event', 'Rose Garden Lunch · 外部审查草稿'],
    'oldest-first sort should use event dates',
  );

  sort.value = 'title';
  sort.listeners.change();
  assert.equal(videos.children.length, 3, 'title sorting should retain all videos');

  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const rankingScript = html.indexOf('assets/main-video-ranking.js');
  const mainVideosScript = html.indexOf('assets/main-videos.js');
  assert.ok(rankingScript >= 0 && rankingScript < mainVideosScript, 'load shared ranking before main videos');
  assert.match(html, /assets\/main-videos\.js\?v=main-video-catalog-3/);
  assert.match(html, /data-main-video-filter="machine"/);
  assert.match(html, /<option value="newest">最新事件<\/option>/);
  assert.match(html, /<option value="popular" disabled>热门（暂无观看量）<\/option>/);
  assert.match(html, /<option value="oldest">最早事件<\/option>/);
  assert.match(html, /<option value="title">标题 A–Z<\/option>/);
  assert.match(html, /没有各作品的可靠观看量，因此不提供误导性的热度排序/);
  assert.ok(
    html.indexOf('id="featured-video"') < html.indexOf('class="panel review-draft-notice"'),
    'put the browsable video catalogue ahead of the secondary review notice',
  );

  const css = fs.readFileSync(path.join(root, 'assets', 'style.css'), 'utf8');
  assert.match(css, /\.main-video-grid\s*\{[^}]*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s);
  assert.match(css, /@media\s*\(max-width:\s*860px\)/);
  assert.match(css, /\.main-video-player\s*\{[^}]*aspect-ratio:\s*16\s*\/\s*9/s);
  assert.match(css, /\.main-video-source-details/);

  const catalog = JSON.parse(
    fs.readFileSync(path.join(root, 'outputs', 'main-videos.json'), 'utf8'),
  );
  assert.ok(Array.isArray(catalog.videos), 'main videos are stored in an extensible catalog');
  assert.equal(catalog.videos[0].id, 'katie-zacharia-2026-10-13-preview-38661270142');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
