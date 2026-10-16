const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(
  path.join(root, 'events/rose-garden-lunch-2026-10-15/index.html'),
  'utf8',
);
const home = fs.readFileSync(path.join(root, 'index.html'), 'utf8');

class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName;
    this.children = [];
    this.attributes = {};
    this.childElementCount = 0;
    this.disabled = false;
    this.listeners = {};
  }

  addEventListener(name, listener) {
    this.listeners[name] = listener;
  }

  append(child) {
    this.children.push(child);
    this.childElementCount = this.children.length;
  }
}

test('home page links to the explicitly public pending review draft', () => {
  assert.match(home, /href="events\/rose-garden-lunch-2026-10-15\/">外部审查草稿/);
  assert.match(home, /公开外部审查草稿 · 尚未审阅/);
});

test('review page discloses pending evidence and does not create an initial YouTube embed', () => {
  assert.doesNotMatch(page, /<iframe\b/i);
  for (const text of [
    '任何人都可以访问',
    '不是完成的制作成品',
    '权利或许可判断',
    '尚未独立核实',
    '来源与事件匹配',
    '中文翻译均未核验',
    '延时效果版本产出与效果审查',
    '未伪造效果或审查结果',
    'IySF_8OArvw',
    'youtube-nocookie.com/embed/IySF_8OArvw',
  ]) {
    assert.ok(page.includes(text), `missing disclosure: ${text}`);
  }
  assert.equal((page.match(/<input type="checkbox" disabled>/g) || []).length, 5);
});

test('YouTube iframe is created only after the explicit accessible button click', () => {
  const inlineScript = page.match(/<script>\s*([\s\S]*?)\s*<\/script>/i)?.[1];
  assert.ok(inlineScript, 'inline click handler should be present');

  const button = new Element('button');
  const player = new Element();
  const status = new Element('p');
  const elements = new Map([
    ['load-review-video', button],
    ['review-video-player', player],
    ['video-load-status', status],
  ]);
  const document = {
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };

  vm.runInNewContext(inlineScript, { document });
  assert.equal(player.childElementCount, 0);
  button.listeners.click();

  assert.equal(player.childElementCount, 1);
  assert.equal(player.children[0].tagName, 'iframe');
  assert.equal(
    player.children[0].src,
    'https://www.youtube-nocookie.com/embed/IySF_8OArvw?autoplay=1&rel=0',
  );
  assert.match(player.children[0].title, /事件匹配未核实/);
  assert.equal(button.disabled, true);
  assert.match(status.textContent, /仍待审/);
});
