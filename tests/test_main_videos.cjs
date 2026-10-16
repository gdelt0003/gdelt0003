const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }
}

async function main() {
  const videos = new Element('div');
  const status = new Element('span');
  const elements = new Map([
    ['mainVideos', videos],
    ['mainVideosStatus', status],
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

  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const rankingScript = html.indexOf('assets/main-video-ranking.js');
  const mainVideosScript = html.indexOf('assets/main-videos.js');
  assert.ok(rankingScript >= 0 && rankingScript < mainVideosScript, 'load shared ranking before main videos');
  assert.match(html, /按事件日期由新到旧排列/);

  const css = fs.readFileSync(path.join(root, 'assets', 'style.css'), 'utf8');
  assert.match(css, /\.main-video-grid\s*\{[^}]*repeat\(auto-fit,\s*minmax\(min\(100%,\s*320px\)/s);
  assert.match(css, /@media\s*\(max-width:\s*680px\)/);
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
