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

test('comparison page renders the public draft with unverified status', async () => {
  const elements = new Map([
    'comparison-rows',
    'event-title',
    'event-subtitle',
    'source-link',
    'pvX-media-status',
    'variant-open-source',
    'variant-microsoft',
  ].map((id) => [id, new Element()]));

  const document = {
    baseURI: 'https://example.github.io/gdelt0003/events/pvXbHQrIvTw/',
    getElementById: (id) => elements.get(id),
    querySelector: (selector) => {
      const match = /^#([^ ]+) \.variant-content$/.exec(selector);
      return match ? (elements.get(match[1]).content ||= new Element()) : null;
    },
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
  assert.match(
    elements.get('variant-open-source').content.children[0].textContent,
    /公开机器生成草稿预览，未经人工核验/,
  );
  assert.match(elements.get('variant-microsoft').content.children[0].textContent, /未用其他模型冒充/);
  const video = elements.get('variant-open-source').content.children.find((node) => node.tagName === 'video');
  assert.ok(video);
  assert.equal(video.src, manifest.smartsub_preview.video_url);
  assert.equal(elements.get('comparison-rows').children.length, 10);
});
