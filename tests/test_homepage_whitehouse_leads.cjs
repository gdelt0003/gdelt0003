const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const sourceFile = path.join(root, 'assets', 'whitehouse-video-leads.js');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.attributes = {};
    this.className = '';
    this.textContent = '';
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

async function runLeadPage(payload, response = { ok: true }) {
  const grid = new Element('div');
  const status = new Element('span');
  const elements = new Map([
    ['officialVideoLeads', grid],
    ['officialVideoLeadsStatus', status],
  ]);
  const document = {
    baseURI: 'https://example.test/site/',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };
  const context = {
    document,
    URL,
    fetch: async (url) => {
      assert.equal(url, 'outputs/whitehouse-discovery.json');
      return {
        ...response,
        json: async () => payload,
      };
    },
    console: { error() {} },
  };
  vm.runInNewContext(fs.readFileSync(sourceFile, 'utf8'), context);
  await new Promise((resolve) => setImmediate(resolve));
  return { grid, status };
}

async function main() {
  const snapshot = JSON.parse(
    fs.readFileSync(path.join(root, 'outputs', 'whitehouse-discovery.json'), 'utf8'),
  );
  const { grid, status } = await runLeadPage(snapshot);
  const actualOfficialEntries = snapshot.leads.filter((lead) => (
    new URL(lead.url).hostname === 'www.youtube.com'
  ));
  const expectedVisible = actualOfficialEntries.slice(0, 10);

  assert.ok(actualOfficialEntries.length >= 10, 'the committed hosted snapshot has enough real official-channel entries');
  assert.equal(grid.children.length, 10, 'show the ten latest usable leads when the feed contains at least ten');
  assert.equal(status.textContent, `显示 10 / ${actualOfficialEntries.length} 条官方频道元数据线索`);
  assert.deepEqual(
    grid.children.map((card) => card.children[0].children[0].textContent),
    expectedVisible.map((lead) => lead.title),
    'preserve the official collector newest-first order without inventing entries',
  );
  assert.deepEqual(
    grid.children.map((card) => card.children[0].children[0].href),
    expectedVisible.map((lead) => lead.url),
    'every entry links to its source video page',
  );
  assert.ok(
    grid.children.every((card) => card.children[2].textContent.includes('元数据线索')),
    'mark every item as metadata-only and unverified',
  );
  assert.ok(
    grid.children[0].children[1].textContent.includes('上传日期未知')
      && grid.children[0].children[1].textContent.includes(snapshot.checked_at_utc.slice(0, 10)),
    'show snapshot date without presenting it as the video upload or event date',
  );
  assert.ok(
    grid.children.every((card) => !card.children.some((child) => child.tagName === 'video')),
    'do not embed or republish media in the metadata-lead catalogue',
  );

  const page = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.match(page, /href="https:\/\/www\.youtube\.com\/@WhiteHouse\/videos"[^>]*>More/);
  assert.match(page, /<link rel="icon" type="image\/svg\+xml" href="favicon\.svg"/);
  assert.ok(fs.existsSync(path.join(root, 'favicon.svg')), 'the explicit homepage favicon must resolve');
  assert.match(page, /assets\/whitehouse-video-leads\.js\?v=metadata-leads-1/);
  assert.match(page, /日期显示为上传元数据或目录快照日期/);
  assert.ok(
    page.indexOf('id="featured-video"') < page.indexOf('id="official-whitehouse-videos"'),
    'keep the existing wide production catalogue separate and before the metadata leads',
  );

  const empty = await runLeadPage({ checked_at_utc: null, leads: [] });
  assert.equal(empty.grid.children.length, 0);
  assert.equal(empty.status.textContent, '暂无可显示的白宫频道视频线索');
  assert.match(empty.grid.textContent, /不代表频道没有其他视频/);

  const failed = await runLeadPage(null, { ok: false, status: 503 });
  assert.equal(failed.status.textContent, '白宫频道元数据线索暂不可用');
  assert.match(failed.grid.textContent, /当前无法读取本地发现快照/);

  const css = fs.readFileSync(path.join(root, 'assets', 'style.css'), 'utf8');
  assert.match(css, /\.official-video-lead-grid\s*\{[^}]*repeat\(auto-fit,\s*minmax\(min\(100%,\s*280px\),\s*1fr\)\)/s);
  assert.match(css, /\.official-video-lead\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.official-video-lead a\s*\{[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(css, /@media\s*\(max-width:\s*600px\)[\s\S]*?\.official-video-leads-actions\s*\{/);

  for (const output of ['whitehouse-discovery.json', 'gdelt-discovery.json', 'published-events.json']) {
    assert.ok(
      fs.existsSync(path.join(root, 'outputs', output)),
      `${output} must exist as a valid Pages asset rather than returning a missing-file 404`,
    );
    assert.doesNotThrow(
      () => JSON.parse(fs.readFileSync(path.join(root, 'outputs', output), 'utf8')),
      `${output} must contain valid JSON`,
    );
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
