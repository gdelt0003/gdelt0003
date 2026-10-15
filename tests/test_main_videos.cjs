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
        id: 'first',
        title: 'First event',
        video_url: 'https://cdn.example.test/first.mp4',
        render_engine: 'Open-source renderer v1',
        render_engine_url: 'https://source.example.test/renderer',
        source_url: 'https://source.example.test/first',
        subtitles: [{ label: 'English SRT', url: 'captions/first.srt' }],
      },
      {
        id: 'second',
        title: 'Second event',
        video_url: 'https://cdn.example.test/second.mp4',
        subtitles: [],
      },
      {
        id: 'unsafe',
        title: 'Unsafe video',
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

  assert.equal(videos.children.length, 2, 'render all safe main videos');
  assert.equal(status.textContent, '2 条主视频', 'count only playable catalog entries');
  assert.equal(videos.children[0].children[1].children[0].textContent, 'First event');
  assert.equal(videos.children[1].children[1].children[0].textContent, 'Second event');
  assert.match(
    videos.children[0].children[1].children.find((node) => node.className === 'main-video-engine').textContent,
    /Open-source renderer v1/,
  );
  assert.equal(
    videos.children[0].children[1].children.find((node) => node.className === 'main-video-engine').children.find((node) => node.tagName === 'a').href,
    'https://source.example.test/renderer',
  );
  assert.equal(
    videos.children[0].children[0].children[0].src,
    'https://cdn.example.test/first.mp4',
  );
  assert.equal(
    videos.children[0].children[1].children.at(-1).children.length,
    3,
    'include MP4, subtitle, and source links',
  );

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
