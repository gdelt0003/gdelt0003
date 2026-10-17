const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName;
    this.children = [];
    this.attributes = attributes;
    this.className = '';
    this.textContent = '';
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }
}

async function main() {
  const sourceDetails = new Element('div', {
    'data-video-id': 'katie-zacharia-2026-10-13-preview-38661270142',
  });
  const status = new Element('span');
  const title = new Element('h2');
  const meta = new Element('p');
  const artifacts = new Element('div');
  const elements = new Map([
    ['mainVideoSourceDetails', sourceDetails],
    ['mainVideoSourceStatus', status],
    ['mainVideoSourceTitle', title],
    ['mainVideoSourceMeta', meta],
    ['mainVideoArtifactDetails', artifacts],
  ]);
  const document = {
    baseURI: 'https://example.test/site/events/katie-zacharia-2026-10-13/sources.html',
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
  };

  const catalog = JSON.parse(
    fs.readFileSync(path.join(root, 'outputs', 'main-videos.json'), 'utf8'),
  );
  const katie = catalog.videos.find((item) => item.id === sourceDetails.getAttribute('data-video-id'));

  let context = {};
  context = {
    document,
    URL,
    fetch: async (url) => {
      assert.equal(url, '../../outputs/main-videos.json');
      return { ok: true, json: async () => catalog };
    },
    console,
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-video-ranking.js'), 'utf8'),
    context,
  );
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'assets', 'main-video-sources.js'), 'utf8'),
    context,
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(katie.provenance.sources.length, 17, 'catalog includes ten event-related video candidates plus two news and five social attribution leads');
  assert.equal(
    katie.provenance.sources.filter((source) => context.MainVideoRanking.inferCategory(source) === 'video').length,
    10,
    'keep ten event-related YouTube video candidates in the ranked list',
  );
  assert.equal(
    katie.provenance.sources.filter((source) => (source.category || context.MainVideoRanking.inferCategory(source)) === 'news').length,
    2,
    'include the direct NBC News and Salon article leads',
  );
  assert.equal(
    katie.provenance.sources.filter((source) => (source.category || context.MainVideoRanking.inferCategory(source)) === 'social').length,
    5,
    'include the attributable social reaction leads without claiming independent verification',
  );
  assert.ok(
    katie.provenance.sources
      .filter((source) => (source.category || context.MainVideoRanking.inferCategory(source)) === 'social')
      .every((source) => source.publish_date === null),
    'social attribution leads keep publish_date null unless the post timestamp is directly verified',
  );
  assert.equal(katie.provenance.sources.filter((source) => source.event_anchor).length, 1);
  assert.equal(katie.provenance.sources.find((source) => source.event_anchor).publisher, 'The White House');
  assert.ok(
    katie.provenance.sources.every((source) => !source.url.includes('bullhead-city')),
    'the unrelated Bullhead City transcript is excluded',
  );

  assert.equal(title.textContent, katie.title);
  assert.equal(meta.textContent, '2026-10-13 · GDELT · process_full_video.py 机器生成预览 · 1920x1080');
  assert.match(status.textContent, /显示 \d+ 条候选来源/);
  assert.match(status.textContent, /按类别分组显示/);

  const categorySections = sourceDetails.children.filter((child) => child.className === 'main-video-source-category');
  assert.equal(categorySections.length, 3, 'show video, news, and social counts even when some categories are empty');
  const videoSection = categorySections.find((section) => section.children[0].textContent.startsWith('视频'));
  const newsSection = categorySections.find((section) => section.children[0].textContent.startsWith('新闻/媒体'));
  const socialSection = categorySections.find((section) => section.children[0].textContent.startsWith('社交/平台'));
  const cards = videoSection.children
    .find((child) => child.className === 'main-video-source-category-list')
    .children.filter((child) => child.className === 'main-video-source');
  const newsCards = newsSection.children
    .find((child) => child.className === 'main-video-source-category-list')
    .children.filter((child) => child.className === 'main-video-source');
  const socialCards = socialSection.children
    .find((child) => child.className === 'main-video-source-category-list')
    .children.filter((child) => child.className === 'main-video-source');
  assert.equal(cards.length, 10, 'render all ten event-related video candidates on the detail page');
  assert.equal(newsCards.length, 2, 'render both direct news article leads');
  assert.equal(socialCards.length, 5, 'render the direct social reaction attribution leads');
  assert.ok(
    newsSection.children[0].textContent.includes('本静态目录当前未收录/本次检索未覆盖'),
    'describe a zero or missing category as a static-directory gap, not as a global absence claim',
  );
  assert.equal(cards[0].children[0].textContent, '#1');
  assert.equal(cards[0].children[1].textContent, 'Press Secretary Katie Zacharia Briefs Members of the Media, Oct. 13, 2026');
  assert.equal(cards[0].children[2].textContent, '事件匹配已确认');
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-evidence-score'
      && child.textContent.includes('记录字段覆盖度:')
      && /\d+\/100/.test(child.textContent)
    )),
    'render a transparent evidence-coverage score for every source',
  );
  assert.ok(
    cards[1].children.some((child) => (
      child.className === 'main-video-source-evidence-basis'
      && child.textContent.includes('unknown/unreviewed:')
      && child.textContent.includes('画面/横幅评估')
    )),
    'name missing evidence criteria as unknown or unreviewed',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-user-score'
      && child.textContent.includes('60/100')
      && child.textContent.includes('用户主观参考分')
    )),
    'keep user-reported scores separate from the evidence coverage score',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-overlay-status'
      && child.textContent.includes('已观察到内嵌横幅/标志')
    )),
    'embedded banners/logos remain distinct from occlusion',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-occlusion-status'
      && child.textContent.includes('记录为未遮挡人脸（仅限已观察部分）')
    )),
    'display limited face-obstruction evidence without generalizing it',
  );
  assert.ok(
    cards.slice(1).every((card) => card.children.some((child) => (
      child.className === 'main-video-source-occlusion-status'
      && child.textContent === '遮挡评估: 未核验'
    ))),
    'unreviewed occlusion remains explicitly unknown',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-trust-note'
      && child.textContent.includes('视频源可信度: 未评估（没有记录评分口径）')
      && child.textContent.includes('视频本身可信度: 未评估')
      && !child.textContent.includes('100/100')
    )),
    'source and video credibility remain separate and are not inferred from field coverage',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-rights'
      && child.textContent.includes('未核实')
    )),
    'reuse rights remain explicit and separate from source trust',
  );
  assert.ok(
    cards[0].children.some((child) => (
      child.className === 'main-video-source-times'
      && child.textContent.includes('发布时间:')
      && child.textContent.includes('事件时间: 未核实')
      && !child.textContent.includes('发布/事件')
    )),
    'publish and event times are displayed separately',
  );

  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-renderer'
      && child.textContent.includes('faster-whisper')
    )),
    'the detail page retains renderer provenance removed from the homepage card',
  );
  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-links'
      && child.children.some((link) => link.textContent === '中英双语 SRT · 未核验')
    )),
    'the detail page retains subtitle downloads',
  );
  assert.ok(
    artifacts.children.some((child) => (
      child.className === 'main-video-artifact-layout'
      && child.textContent.includes('configured_not_rendered')
    )),
    'the detail page retains subtitle layout review state',
  );

  const grouping = context.MainVideoRanking.groupByCategory([
    { id: 'v1', category: 'video', title: 'Video A', url: 'https://example.test/video-a', max_resolution: '1920x1080', duration_seconds: 180, overlay_status: 'overlay_present' },
    { id: 'n1', category: 'news', title: 'News A', url: 'https://example.test/news-a', max_resolution: '1280x720', duration_seconds: 120, publish_date: '2026-10-13', overlay_status: 'unassessed' },
    { id: 's1', category: 'social', title: 'Social A', url: 'https://x.com/example', max_resolution: '720x480', duration_seconds: 30 },
    { id: 'o1', category: 'other', title: 'Other A', url: 'https://example.test/other-a' },
  ]);
  assert.equal(grouping.length, 4, 'group the ranked sources by video, news, social, and other when present');
  assert.equal(grouping[0].category, 'video');
  assert.equal(grouping[1].category, 'news');
  assert.equal(grouping[2].category, 'social');
  assert.equal(grouping[3].category, 'other');
  assert.ok(grouping.every((group) => group.sources.length > 0), 'each category with sources should render its own section');

  const manyVideoSources = Array.from({ length: 25 }, (_, index) => ({
    id: `video-${index}`,
    category: 'video',
    title: `Video ${index}`,
    url: `https://example.test/video-${index}`,
  }));
  const unboundedGroups = context.MainVideoRanking.groupByCategory(manyVideoSources);
  assert.equal(unboundedGroups[0].total, 25, 'category count includes every source without a top-ten cap');
  assert.equal(unboundedGroups[0].sources.length, 25, 'render every source in a category, including more than ten');

  const unknownReview = context.MainVideoRanking.evidenceScore({
    url: 'https://example.test/unknown-review',
    title: 'Unknown review status',
    overlay_status: 'unassessed',
    caption_provenance: { verification: '未核验' },
  });
  assert.equal(unknownReview.checks.find((check) => check.label === 'overlay_review').passes, false);
  assert.equal(unknownReview.checks.find((check) => check.label === 'caption_review').passes, false);

  const withoutAnchor = Array.from({ length: 11 }, (_, index) => ({
    id: `candidate-${index}`,
    classification: 'confirmed',
    overlay_status: 'clear_verified',
    max_resolution: '3840x2160',
    duration_seconds: 10000 - index,
    view_count: 100000 - index,
  }));
  const anchor = {
    id: 'official-anchor',
    event_anchor: true,
    classification: 'confirmed',
    overlay_status: 'overlay_present',
    max_resolution: '1280x720',
    duration_seconds: 10,
    view_count: 1,
  };
  const ranked = context.MainVideoRanking.rank([...withoutAnchor, anchor]);
  assert.equal(ranked.length, 12, 'no global hard cap; every ranked source remains visible');
  assert.equal(ranked[0].id, 'official-anchor', 'retain the official anchor without slicing to ten');
  assert.ok(ranked.some((source) => source.event_anchor), 'official event anchor stays ranked');

  const partial = { title: 'Incomplete lead', url: 'https://example.test/partial', classification: 'lead', overlay_status: 'unassessed' };
  const partialScore = context.MainVideoRanking.evidenceScore(partial);
  assert.ok(partialScore.score < 100, 'unknown evidence stays below the full score');
  assert.ok(partialScore.unknowns.length > 0, 'unknown fields stay explicit instead of becoming fabricated certainty');

  const subjectiveSource = {
    caption_provenance: { user_given_reference_score: 60, user_score_note: '用户参考分，不计入证据覆盖分' },
    url: 'https://example.test/subjective',
    title: 'Subjective lead',
    publish_date: '2026-10-13',
    overlay_status: 'unassessed',
  };
  const subjective = context.MainVideoRanking.userSubjectiveScore(subjectiveSource);
  assert.equal(subjective.value, 60);
  assert.match(subjective.note, /不计入证据覆盖分/);

  const page = fs.readFileSync(
    path.join(root, 'events', 'katie-zacharia-2026-10-13', 'sources.html'),
    'utf8',
  );
  assert.match(page, /视频源可信度与视频本身可信度/);
  assert.match(page, /不执行实时检索、夜间复核或自动验证/);
  assert.match(page, /记录字段覆盖度 0–100/);
  assert.match(page, /不是可信度、真实性或质量评分/);
  assert.match(page, /0.*不代表全网不存在/);
  assert.match(page, /本静态目录当前未收录\/本次检索未覆盖/);
  assert.match(page, /本静态快照中未检出更多已核验候选/);
  assert.match(page, /按视频\/新闻\/社交\/其他类别分组/);
  assert.match(page, /main-video-ranking\.js/);
  assert.match(page, /main-video-sources\.js/);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
