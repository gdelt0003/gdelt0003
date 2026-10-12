const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '..', 'assets', 'app.js'), 'utf8');

function element(tagName = 'div') {
  return {
    tagName: tagName.toUpperCase(),
    children: [],
    listeners: {},
    value: '',
    checked: true,
    hidden: false,
    disabled: false,
    textContent: '',
    href: '',
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    addEventListener(name, listener) { this.listeners[name] = listener; },
    setAttribute() {},
    scrollIntoView() {},
    focus() {},
    select() {},
  };
}

async function startApp(catalog) {
  const ids = [
    'videoGrid', 'status', 'refreshBtn', 'searchInput', 'resultSummary', 'pagination',
    'sourceDetails', 'sourceList', 'searchMode', 'sourceFilter', 'workflowVideoUrl',
    'workflowLanguages', 'workflowDuration', 'workflowStyle', 'workflowExampleUrl', 'workflowPrivacy',
    'workflowBroll', 'prepareWorkflowBtn', 'copyWorkflowSettingsBtn', 'workflowSettings',
  ];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  const searchFields = ['title', 'author', 'description', 'source'].map(value => ({
    ...element('input'), value, checked: true,
  }));
  const workflowPlatforms = ['youtube', 'tiktok', 'instagram', 'facebook', 'x'].map(value => ({
    ...element('input'), value, checked: false,
  }));
  const selectors = {
    'input[name="searchField"]': searchFields,
    'input[name="workflowPlatform"]': workflowPlatforms,
  };
  const historyEntries = [];
  const sandbox = {
    document: {
      getElementById: id => elements[id],
      querySelectorAll: selector => selectors[selector] || [],
      createElement: tagName => element(tagName),
    },
    location: { search: '', pathname: '/' },
    history: { replaceState: (_state, _title, url) => historyEntries.push(url) },
    fetch: async () => ({ ok: true, json: async () => catalog }),
    URL,
    URLSearchParams,
    navigator: { clipboard: { writeText: async () => {} } },
    Date,
    Number,
    Math,
    String,
    Array,
    Set,
    RegExp,
    console,
  };
  vm.runInNewContext(appSource, sandbox);
  await new Promise(resolve => setImmediate(resolve));
  return { elements, searchFields, workflowPlatforms, historyEntries };
}

const sampleCatalog = {
  generatedAt: '2026-10-12T00:00:00Z',
  sources: [],
  shorts: [],
  videos: [
    {
      id: 'video001', title: 'North update', author: 'Channel A', description: 'Local story',
      source: 'https://www.youtube.com/@one/videos', url: 'https://youtube.com/watch?v=video001',
    },
    {
      id: 'video002', title: 'West briefing', author: 'Channel B', description: 'Global story',
      source: 'https://www.youtube.com/@two/videos', url: 'https://youtube.com/watch?v=video002',
    },
  ],
};

test('multi-keyword matching supports AND and OR across selected fields', async () => {
  const app = await startApp(sampleCatalog);
  app.elements.searchInput.value = 'north west';
  app.elements.searchInput.listeners.input();
  assert.equal(app.elements.resultSummary.textContent, '0 videos');
  app.elements.searchMode.value = 'or';
  app.elements.searchMode.listeners.change();
  assert.equal(app.elements.resultSummary.textContent, 'Showing 1–2 of 2 videos');

  app.searchFields.find(field => field.value === 'title').checked = false;
  app.searchFields.find(field => field.value === 'description').checked = false;
  app.searchFields.find(field => field.value === 'source').checked = false;
  app.elements.searchMode.value = 'and';
  app.elements.searchInput.value = 'Channel B';
  app.elements.searchInput.listeners.input();
  assert.equal(app.elements.resultSummary.textContent, 'Showing 1–1 of 1 videos');
  app.searchFields.find(field => field.value === 'author').checked = false;
  app.elements.searchInput.listeners.input();
  assert.equal(app.elements.resultSummary.textContent, '0 videos');

  app.elements.searchInput.value = '';
  app.elements.searchInput.listeners.input();
  assert.equal(app.elements.resultSummary.textContent, 'Showing 1–2 of 2 videos');

  app.searchFields.find(field => field.value === 'title').checked = true;
  app.searchFields.find(field => field.value === 'description').checked = true;
  app.elements.searchInput.value = 'north local';
  app.elements.searchInput.listeners.input();
  assert.equal(app.elements.resultSummary.textContent, 'Showing 1–1 of 1 videos');
});

test('source selector filters results and search state is URL-addressable', async () => {
  const app = await startApp(sampleCatalog);
  app.elements.sourceFilter.value = 'https://www.youtube.com/@one/videos';
  app.elements.sourceFilter.listeners.change();
  assert.equal(app.elements.resultSummary.textContent, 'Showing 1–1 of 1 videos');
  assert.match(app.historyEntries.at(-1), /source=https/);
});

test('creator controls prepare explicit workflow input names without credentials', async () => {
  const app = await startApp(sampleCatalog);
  app.elements.workflowVideoUrl.value = 'https://youtube.com/watch?v=video001';
  app.elements.workflowLanguages.value = 'es-ES';
  app.elements.workflowStyle.value = 'match-example';
  app.workflowPlatforms.find(platform => platform.value === 'youtube').checked = true;
  app.elements.prepareWorkflowBtn.listeners.click();
  assert.match(app.elements.workflowSettings.value, /short_video_url: https:\/\/youtube.com\/watch\?v=video001/);
  assert.match(app.elements.workflowSettings.value, /clip_authorized: confirm manually in Actions/);
  assert.match(app.elements.workflowSettings.value, /publish_to: youtube/);
  assert.match(app.elements.workflowSettings.value, /clip_duration_seconds: 45/);
});
