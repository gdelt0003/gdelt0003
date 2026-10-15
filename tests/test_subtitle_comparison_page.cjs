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
  assert.equal(pathways.at(-1).dataset.kind, 'copilot_engineering');
  assert.match(pathways.at(-1).children[1].textContent, /Copilot coding-agent/);
  assert.equal(elements.get('comparisonRows').children.length, 5);
  assert.match(elements.get('comparisonRows').children.at(-1).children[2].textContent, /不据此否认 agent 可调用 GPT-6/);
});
