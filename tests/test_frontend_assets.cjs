const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const outputDirectory = './outputs/whitehouse-oct-06-2026/';
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, outputDirectory, 'manifest.json'), 'utf8'),
);

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.style = {};
    this.listeners = {};
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }
}

const elements = new Map([
  ['highlightGrid', new Element('div')],
  ['highlightsStatus', new Element('div')],
]);
const document = {
  getElementById: (id) => elements.get(id),
  createElement: (tagName) => new Element(tagName),
};
const context = {
  document,
  fetch: async () => ({ ok: true, json: async () => manifest }),
  console,
};

async function main() {
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'app.js'), 'utf8'),
    context,
  );
  await new Promise((resolve) => setImmediate(resolve));

  const cards = elements.get('highlightGrid').children;
  const expectedCount = manifest.highlights.reduce(
    (count, highlight) => count + highlight.variants.length,
    0,
  );
  assert.equal(cards.length, expectedCount, 'all manifest clips should render');

  for (const card of cards) {
    const player = card.children[0];
    const source = player.children[0];
    const info = card.children[1];
    const download = info.children.find((child) => child.className === 'clip-link');
    const relativePath = source.src.replace(/^\.\//, '');
    const variant = manifest.highlights
      .flatMap((highlight) => highlight.variants)
      .find((item) => item.file === path.basename(source.src));

    assert.ok(variant, `playback asset should be listed in the manifest: ${source.src}`);
    const dimensions = /^(\d+)x(\d+)$/i.exec(variant.resolution || '');

    assert.equal(source.src, download.href, 'playback and download must use the same URL');
    assert.ok(
      source.src.startsWith(outputDirectory),
      `playback URL must include the output directory: ${source.src}`,
    );
    assert.ok(
      fs.existsSync(path.join(root, relativePath)),
      `playback asset must exist: ${source.src}`,
    );
    assert.ok(dimensions, `manifest resolution should be present for ${source.src}`);
    assert.equal(
      player.style.aspectRatio,
      `${dimensions[1]} / ${dimensions[2]}`,
      'player should use the clip aspect ratio before metadata loads',
    );
  }

  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const resultsPage = fs.readFileSync(path.join(root, 'copilot-results.html'), 'utf8');
  const css = fs.readFileSync(path.join(root, 'assets', 'style.css'), 'utf8');
  assert.doesNotMatch(html, /<track\b/i, 'do not overlay duplicate, unverified captions');
  assert.match(html, /assets\/style\.css\?v=whitehouse-8/);
  assert.match(html, /href="copilot-results\.html">Copilot 成果<\/a>/, 'link homepage navigation to the results page');
  assert.doesNotMatch(html, /class="copilot-result-card"/, 'keep the full results panel off the homepage');
  assert.doesNotMatch(html, /id="copilot-results"/, 'remove the results section from the homepage');
  assert.match(resultsPage, /assets\/style\.css\?v=whitehouse-7/);
  assert.match(resultsPage, /id="copilot-results"/, 'show the Copilot results section on its dedicated page');
  assert.match(resultsPage, /不把开源媒体工具的代码或生成结果冒领为微软成果/);
  assert.equal([...resultsPage.matchAll(/class="copilot-result-card"/g)].length, 3, 'keep all result cards on the dedicated page');
  for (const url of [
    'https://github.com/gdelt0003/gdelt0003/pull/21',
    'https://github.com/gdelt0003/gdelt0003/actions/runs/38540536544',
    'https://github.com/gdelt0003/gdelt0003/pull/23',
    'https://github.com/gdelt0003/gdelt0003/pull/25',
    'https://github.com/gdelt0003/gdelt0003/actions/runs/38544067659',
  ]) {
    assert.ok(resultsPage.includes(url), `preserve existing result link: ${url}`);
  }
  assert.match(html, /events\/pvXbHQrIvTw\/#pathways/, 'keep pathway comparison on the dedicated event page');
  assert.match(html, /id="mainVideos"/, 'main videos should render into a catalog');
  assert.match(html, /assets\/main-videos\.js/);
  assert.match(html, /竖屏 9:16/);
  assert.doesNotMatch(html, /全长视频.{0,40}1080 × 1920/);
  assert.match(css, /\.clip-player\s*\{[^}]*aspect-ratio:\s*9\s*\/\s*16/s);
  assert.match(css, /\.main-video-player\s*\{[^}]*aspect-ratio:\s*16\s*\/\s*9/s);
  assert.match(css, /\.main-video-grid\s*\{[^}]*display:\s*grid/s);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
