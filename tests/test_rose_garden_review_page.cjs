const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(
  path.join(root, 'events/rose-garden-lunch-2026-10-15/index.html'),
  'utf8',
);
const styles = fs.readFileSync(path.join(root, 'assets/style.css'), 'utf8');
const home = fs.readFileSync(path.join(root, 'index.html'), 'utf8');

test('home page links to the explicitly public pending review draft', () => {
  assert.match(home, /href="events\/rose-garden-lunch-2026-10-15\/">外部审查草稿/);
  assert.match(home, /公开外部审查草稿 · 尚未审阅/);
});

test('review page uses the burned public MP4 rather than the YouTube source as its player', () => {
  assert.doesNotMatch(page, /<iframe\b/i);
  assert.match(page, /<video controls preload="none" playsinline/);
  assert.match(
    page,
    /<source src="https:\/\/github\.com\/gdelt0003\/gdelt0003\/releases\/download\/rose-garden-lunch-review\/RoseGardenLunch-IySF_8OArvw-bilingual\.mp4" type="video\/mp4">/,
  );
  assert.match(
    page,
    /查看提交的 YouTube 原始来源（次要来源链接）/,
  );
  assert.match(page, /提交者已授权对指定视频进行云端处理并公开为外部审查稿/);
  assert.match(page, /不等于独立法律审查/);
  for (const text of [
    '任何人都可以访问',
    '不是完成的制作成品',
    '尚未独立核实',
    '来源与事件匹配',
    '原片画面及嵌入图文检查',
    '原片音频及英语 ASR 准确性',
    '中文翻译忠实度与可读性',
    '独立权利/许可及潜在第三方内容审查',
    'ASR 与机器翻译未经人工核验',
    'IySF_8OArvw',
  ]) {
    assert.ok(page.includes(text), `missing disclosure: ${text}`);
  }
  assert.equal((page.match(/<input type="checkbox" disabled>/g) || []).length, 5);
});

test('review page presents a compact, accessible video-first layout', () => {
  assert.match(page, /<nav class="main-video-detail-nav review-breadcrumb" aria-label="页面导航">/);
  assert.match(page, /<h1 id="review-title">Rose Garden Lunch<span class="review-title-subline">公开外部审查草稿<\/span><\/h1>/);
  assert.match(page, /<div class="review-status-row" role="group" aria-label="当前状态">/);
  assert.match(page, /待外部审查/);
  assert.match(page, /尚未获发布批准/);
  assert.match(page, /来源与事件未核验/);
  assert.match(page, /ASR\/翻译未人工核验/);
  assert.match(page, /权利\/许可待独立审查/);
  assert.match(page, /<details class="review-disclosures">/);
  assert.match(page, /<summary>审查范围、来源状态与授权说明/);
  assert.match(page, /<aside class="review-video-info" aria-label="审查视频信息">/);
  assert.match(page, /<dl class="review-video-meta">/);
  assert.match(page, /<span data-review-status>待审<\/span>/);

  assert.match(styles, /\.review-page \{ max-width: 1600px; \}/);
  assert.match(styles, /\.review-header > p, \.review-section > p \{ max-width: 76ch; \}/);
  assert.match(styles, /\.review-video-layout \{ display: grid; grid-template-columns: minmax\(0, 1\.85fr\) minmax\(230px, \.85fr\);/);
  assert.match(styles, /\.review-video video \{[^}]*aspect-ratio: 16 \/ 9;/);
  assert.match(styles, /@media \(max-width: 860px\) \{[\s\S]*?\.review-video-layout \{ grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(styles, /@media \(max-width: 600px\) \{\s+\.review-page \{ padding: 16px 12px 40px; \}/);
  assert.match(styles, /\.review-page button:focus-visible, \.review-page a:focus-visible, \.review-page summary:focus-visible/);
});
