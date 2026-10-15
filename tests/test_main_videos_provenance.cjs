const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = '';
    this.textContent = '';
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  findChildByClass(className) {
    return this.children.find((c) => c.className === className);
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

  const catalogRaw = fs.readFileSync(path.join(root, 'outputs', 'main-videos.json'), 'utf8');
  const catalog = JSON.parse(catalogRaw);

  const context = {
    document,
    URL,
    fetch: async () => ({ ok: true, json: async () => catalog }),
    console,
  };

  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-videos.js'), 'utf8'),
    context,
  );
  await new Promise((resolve) => setImmediate(resolve));

  // there should be at least one rendered main video
  assert.ok(videos.children.length >= 1, 'at least one main video rendered');

  const firstContent = videos.children[0].children[1];
  assert.ok(firstContent, 'first video content exists');

  const sourcesWrap = firstContent.children.find((n) => n.className === 'main-video-sources');
  assert.ok(sourcesWrap, 'provenance sources panel rendered');

  // verify top-10 cap (count only .main-video-source children; heading is excluded)
  const sourceCards = sourcesWrap.children.filter((c) => c.className === 'main-video-source');
  assert.ok(sourceCards.length <= 10, `top-10 cap enforced (found ${sourceCards.length})`);

  // ensure Roll Call transcript is not present as a video source (search only in source cards)
  const rollcall = sourceCards.find((c) => c.textContent && c.textContent.includes('Roll Call'));
  assert.equal(rollcall, undefined, 'Roll Call transcript should not be present as a source video');

  // check for source trust note text in at least one source (whitehouse entry)
  // search child nodes for the trust note text (test harness elements keep textContent on leaf nodes)
  const trustNoteFound = sourceCards.some((card) => (
    (card.textContent && card.textContent.includes('未评分（评分口径未提供）')) ||
    card.children.some((child) => (child.textContent || '').includes('未评分（评分口径未提供）'))
  ));
  assert.ok(trustNoteFound, 'source trust note should appear when present');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
