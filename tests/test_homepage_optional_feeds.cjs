const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.attributes = {};
    this.textContent = '';
    this.className = '';
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
    this.textContent = '';
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }
}

async function runEventsPage(failRequests = false) {
  const elements = new Map(
    ['eventCatalog', 'eventDiscovery', 'eventDiscoveryStatus', 'publishedEvents', 'publishedEventsStatus']
      .map((id) => [id, new Element('div')]),
  );
  const requested = [];
  const document = {
    baseURI: 'https://example.test/site/',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };
  const context = {
    document,
    URL,
    console: { error() {} },
    fetch: async (url) => {
      requested.push(url);
      if (failRequests) return { ok: false, status: 503 };
      const file = path.join(root, url);
      return {
        ok: fs.existsSync(file),
        status: fs.existsSync(file) ? 200 : 404,
        json: async () => JSON.parse(fs.readFileSync(file, 'utf8')),
      };
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'assets', 'events.js'), 'utf8'), context);
  await new Promise((resolve) => setImmediate(resolve));
  return { elements, requested };
}

async function main() {
  const { elements, requested } = await runEventsPage();
  assert.deepEqual(
    requested,
    [
      'outputs/event-catalog.json',
      'outputs/whitehouse-discovery.json',
      'outputs/gdelt-discovery.json',
      'outputs/published-events.json',
    ],
    'all homepage feed URLs resolve to committed static assets',
  );
  assert.match(elements.get('eventDiscoveryStatus').textContent, /20 条白宫视频线索/);
  assert.match(elements.get('eventDiscoveryStatus').textContent, /GDELT 暂无成功快照/);
  assert.ok(elements.get('eventDiscovery').children.length >= 20, 'keep the real White House metadata leads visible');
  assert.equal(elements.get('publishedEventsStatus').textContent, '0 个事件版本 · 0 支短片');
  assert.match(elements.get('publishedEvents').textContent, /暂无登记为已发布并通过复核/);

  const failed = await runEventsPage(true);
  assert.match(failed.elements.get('eventDiscoveryStatus').textContent, /检索结果暂不可用/);
  assert.match(failed.elements.get('eventDiscovery').textContent, /只进入未分配线索/);
  assert.equal(failed.elements.get('publishedEventsStatus').textContent, '已发布作品暂不可用');
  assert.match(failed.elements.get('publishedEvents').textContent, /不会将发现线索或处理草稿显示为已发布作品/);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
