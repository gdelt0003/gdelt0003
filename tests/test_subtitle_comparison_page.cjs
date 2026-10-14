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
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
    this.textContent = '';
  }
}

test('comparison page renders pending states without claiming generated media', async () => {
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
  assert.equal(elements.get('variant-open-source').content.children[0].textContent, '未运行：等待具备授权的云端处理与复核。');
  assert.match(elements.get('variant-microsoft').content.children[0].textContent, /未用其他模型冒充/);
  assert.equal(elements.get('variant-open-source').content.children.some((node) => node.tagName === 'video'), false);
  assert.equal(elements.get('comparison-rows').children.length, 10);
});
