const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName;
    this.children = [];
    this.attributes = attributes;
    this.className = '';
    this.textContent = '';
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }
}

async function main() {
  const sourceDetails = new Element('div', {
    'data-video-id': 'katie-zacharia-2026-10-13-preview-38661270142',
  });
  const status = new Element('span');
  const title = new Element('h2');
  const meta = new Element('p');
  const artifacts = new Element('div');
  const elements = new Map([
    ['mainVideoSourceDetails', sourceDetails],
    ['mainVideoSourceStatus', status],
    ['mainVideoSourceTitle', title],
    ['mainVideoSourceMeta', meta],
    ['mainVideoArtifactDetails', artifacts],
  ]);
  const document = {
    baseURI: 'https://example.test/site/events/katie-zacharia-2026-10-13/sources.html',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };

  const catalog = JSON.parse(
    fs.readFileSync(path.join(root, 'outputs', 'main-videos.json'), 'utf8'),
  );
  const katie = catalog.videos.find((item) => item.id === sourceDetails.getAttribute('data-video-id'));
  assert.equal(katie.provenance.sources.length, 10, 'catalog contains ten event-related video candidates');
  assert.ok(
    katie.provenance.sources.every((source) => new URL(source.url).hostname === 'www.youtube.com'),
    'only event-related YouTube video pages are included in the ranked list',
  );
  assert.equal(katie.provenance.sources.filter((source) => source.event_anchor).length, 1);
  assert.equal(katie.provenance.sources.find((source) => source.event_anchor).publisher, 'The White House');
  assert.ok(
    katie.provenance.sources.every((source) => !source.url.includes('bullhead-city')),
    'the unrelated Bullhead City transcript is excluded',
  );

  const context = {
    document,
    URL,
    fetch: async (url) => {
      assert.equal(url, '../../outputs/main-videos.json');
      return { ok: true, json: async () => catalog };
    },
    console,
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-video-ranking.js'), 'utf8'),
    context,
  );
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-video-sources.js'), 'utf8'),
    context,
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(title.textContent, katie.title);
  assert.equal(meta.textContent, '2026-10-13 · GDELT · process_full_video.py 机器生成预览 · 1920x1080');
  assert.equal(status.textContent, '显示 10 条候选来源（最多 10 条）');
  const cards = sourceDetails.children.filter((child) => child.className === 'main-video-source');
  assert.equal(cards.length, 10, 'render all ten event-related video candidates on the detail page');
  assert.equal(cards[0].children[0].textContent, '#1');
  assert.equal(cards[0].children[1].textContent, 'Press Secretary Katie Zacharia Briefs Members of the Media, Oct. 13, 2026');
  assert.equal(cards[0].children[2].textContent, '事件匹配已确认');
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-overlay-status'
      && child.textContent.includes('已观察到内嵌横幅/标志')
    )),
    'embedded banners/logos remain distinct from occlusion',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-occlusion-status'
      && child.textContent.includes('记录为未遮挡人脸（仅限已观察部分）')
    )),
    'display limited face-obstruction evidence without generalizing it',
  );
  assert.ok(
    cards.slice(1).every((card) => card.children.some((child) => (
      child.className === 'main-video-source-occlusion-status'
      && child.textContent === '遮挡评估: 未核验'
    ))),
    'unreviewed occlusion remains explicitly unknown',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-trust-note'
      && child.textContent.includes('未评分（评分口径未提供）')
    )),
    'source trust remains unrated rather than fabricated',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-rights'
      && child.textContent.includes('未核实')
    )),
    'reuse rights remain explicit and separate from source trust',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-times'
      && child.textContent.includes('发布时间:')
      && child.textContent.includes('事件时间: 未核实')
      && !child.textContent.includes('发布/事件')
    )),
    'publish and event times are displayed separately',
  );

  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-renderer'
      && child.textContent.includes('faster-whisper')
    )),
    'the detail page retains renderer provenance removed from the homepage card',
  );
  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-links'
      && child.children.some((link) => link.textContent === '中英双语 SRT · 未核验')
    )),
    'the detail page retains subtitle downloads',
  );
  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-layout'
      && child.textContent.includes('configured_not_rendered')
    )),
    'the detail page retains subtitle layout review state',
  );

  const withoutAnchor = Array.from({ length: 11 }, (_, index) => ({
    id: `candidate-${index}`,
    classification: 'confirmed',
    overlay_status: 'clear_verified',
    max_resolution: '3840x2160',
    duration_seconds: 10000 - index,
    view_count: 100000 - index,
  }));
  const anchor = {
    id: 'official-anchor',
    event_anchor: true,
    classification: 'confirmed',
    overlay_status: 'overlay_present',
    max_resolution: '1280x720',
    duration_seconds: 10,
    view_count: 1,
  };
  const topTen = context.MainVideoRanking.rank([...withoutAnchor, anchor]);
  assert.equal(topTen.length, 10);
  assert.equal(topTen[0].id, 'official-anchor', 'retain and pin the official event anchor when capping');
  assert.ok(topTen.some((source) => source.event_anchor), 'official event anchor stays in the top ten');

  const page = fs.readFileSync(
    path.join(root, 'events', 'katie-zacharia-2026-10-13', 'sources.html'),
    'utf8',
  );
  assert.match(page, /来源与版本信心/);
  assert.match(page, /不执行实时检索、夜间复核或自动验证/);
  assert.match(page, /遮挡状态未核验，不代表画面无遮挡/);
  assert.match(page, /main-video-ranking\.js/);
  assert.match(page, /main-video-sources\.js/);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
