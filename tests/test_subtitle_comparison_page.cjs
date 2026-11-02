const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, 'outputs/pvXbHQrIvTw/comparison.json'), 'utf8'),
);

class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.textContent = '';
    this.href = '';
    this.attributes = {};
  }

  append(...children) {
    this.children.push(...children);
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  replaceChildren(...children) {
    this.children = [...children];
    this.textContent = '';
  }
}

test('comparison page separates open-source media routes from Copilot engineering results', async () => {
  const elements = new Map([
    'event-title',
    'event-subtitle',
    'source-link',
    'pvX-media-status',
    'pathwayGrid',
    'comparisonRows',
  ].map((id) => [id, new Element()]));

  const document = {
    baseURI: 'https://example.github.io/gdelt0003/events/pvXbHQrIvTw/',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };

  const source = fs.readFileSync(path.join(root, 'assets/comparison.js'), 'utf8');
  vm.runInNewContext(source, {
    document,
    URL,
    fetch: async () => ({ ok: true, json: async () => manifest }),
    console,
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.match(elements.get('event-title').textContent, /Oct\. 13, 2026/);
  assert.equal(elements.get('source-link').href, manifest.event.source_url);
  const pathways = elements.get('pathwayGrid').children;
  assert.equal(pathways.length, manifest.pathways.length + 1);
  assert.match(pathways[0].children[2].textContent, /已运行 · 草稿未通过人工核验/);
  assert.equal(pathways[0].children.some((node) => node.tagName === 'video'), true);
  assert.equal(pathways[0].children.find((node) => node.tagName === 'video').src, manifest.smartsub_preview.video_url);
  assert.match(pathways[1].children[2].textContent, /受阻 · 未运行/);
  assert.equal(pathways[2].children.some((node) => node.textContent === '上游仓库许可证：GPL-3.0'), true);
  assert.equal(
    pathways[2].children.some((node) => node.children.some((child) => child.href === manifest.pathways[2].license_url)),
    true,
  );
  assert.match(pathways[3].children[2].textContent, /研究候选 · 未运行/);
  assert.equal(pathways[3].children.some((node) => /许可证未确认/.test(node.textContent)), true);
  assert.equal(
    pathways[3].children.some((node) => node.children.some((child) => child.href === manifest.pathways[3].source_hub_url)),
    true,
  );
  assert.match(pathways[4].children[2].textContent, /无处理该媒体的证据/);
  assert.equal(pathways.at(-1).dataset.kind, 'copilot_engineering');
  assert.match(pathways.at(-1).children[0].textContent, /REPOSITORY ENGINEERING/);
  assert.match(pathways.at(-1).children[1].textContent, /Copilot coding-agent/);
  assert.equal(elements.get('comparisonRows').children.length, 5);
  assert.match(elements.get('comparisonRows').children[1].children[1].textContent, /SmartSub 3\.9\.0/);
  assert.match(elements.get('comparisonRows').children[1].children[2].textContent, /coding-agent 未渲染此视频/);
});
