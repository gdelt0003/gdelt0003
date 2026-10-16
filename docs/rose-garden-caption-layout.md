# M3 bilingual caption layout profile

**Status:** M3 engineering profile, version 1.0. It is a documented project
recommendation, not a law, WCAG requirement, or universal industry standard.
Use it for landscape 16:9 English/Simplified Chinese open-caption renders unless
an approved delivery specification says otherwise.

## Authority and scope

| Source | What it establishes | What it does not establish |
| --- | --- | --- |
| [WCAG 2.2, SC 1.2.2 Captions (Prerecorded)](https://www.w3.org/TR/WCAG22/#captions-prerecorded) and [SC 1.2.4 Captions (Live)](https://www.w3.org/TR/WCAG22/#captions-live) | Conformance criteria for synchronized captions in prerecorded and live media. WCAG's [caption definition](https://www.w3.org/TR/WCAG22/#dfn-captions) includes speech and meaningful non-speech audio; its note says captions should not obscure or obstruct relevant video information. | A prescribed font, font-size ratio, line count, safe-area percentage, or subtitle background opacity. |
| [W3C IMSC 1.2](https://www.w3.org/TR/ttml-imsc1.2/) | A TTML profile for interoperable subtitle/caption documents, including timing, regions, styling, and presentation constraints. Use its applicable profile and conformance clauses when delivering IMSC/TTML. | A universal visual design for captions burned into an MP4, or permission to cover source graphics. The implementation in this repository emits ASS and must not be described as IMSC-conformant. |
| [BBC Subtitle Guidelines, v1.2.5](https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/) — sections **Line lengths**, **Fonts**, **Authoring font size**, **Positioning**, and **Backgrounds** | BBC's own editorial and platform guidance. For online landscape 16:9, it recommends a maximum line length of 68% of video width, up to two lines, a central 75% horizontal and central 90% vertical placement area, and a 7–8% active-picture-height line height. It prefers bottom positioning but explicitly prioritizes keeping on-screen captions, mouths, and important action visible. Its font-size and device-scaling guidance is also BBC guidance. | A rule binding all publishers. The guide itself describes guidelines and practical advice whose application depends on content and expertise. |
| [Netflix Timed Text Style Guide — General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements), sections **4 Line Treatment**, **5 Positioning**, and **13 Technical Aspects**; [English (USA) guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide), sections **I.7 Font Information** and **I.10 Line Treatment** | Requirements for deliveries made to Netflix: at most two lines, linguistically sensible line breaks, top/bottom centered positioning with avoidance of on-screen text, and percentage-based TTML positioning. The English-USA guide gives its own font and character-fit guidance. | A general requirement for this repository, other platforms, or burned-in captions. |
| [WCAG 2.2, SC 1.4.3 Contrast (Minimum)](https://www.w3.org/TR/WCAG22/#contrast-minimum) | A 4.5:1 contrast criterion for normal text and 3:1 for large text where that success criterion applies. | A caption-specific opacity value. Measure contrast against the actual rendered background; an opacity percentage alone does not prove contrast. |

These sources have different authority. WCAG success criteria are normative
when a conformance claim is being made; IMSC is normative for documents claiming
the relevant IMSC profile; BBC and Netflix publish organization/platform
guidance. The numeric design choices below are M3's project profile and must
not be attributed to WCAG or presented as universal industry requirements.

## M3 project profile

| Property | M3 implementation recommendation |
| --- | --- |
| Picture and graphics | Preserve the source frame dimensions and contents except for the separately authorized Rose Garden mask exception below. General M3 layouts must not crop, paint over, or place captions over source lower-thirds, logos, tickers, names, faces, mouths, or important action. Use human-reviewed protected BBoxes and fail closed on a collision. |
| Safe area | For 16:9 online output, keep text within the central 75% horizontally and central 90% vertically, following BBC online guidance. Use a per-line width target no greater than 68% of active picture width, also following BBC's landscape online line-length recommendation. Account for player controls by moving the region when controls are present. |
| Default position | Center-align prepared captions and start near the bottom only when the source frame has room. Reposition vertically or horizontally to avoid graphics, faces, mouths, and action. Content visibility takes priority over a fixed lower-third position. |
| Font | Use a clear sans-serif with reliable Latin and Simplified Chinese glyph coverage. Use the same typographic family where available; do not substitute missing Chinese glyphs with tofu or silently drop characters. Choose a wide authoring font and verify the actual renderer's output width. |
| Size and line height | Derive size from the active video height, not a hard-coded pixel size. For landscape 16:9, target a line height of 7–8% of active picture height, using BBC's authoring guidance as a reference. A player may scale captions for device/viewing distance; where the renderer cannot scale, verify at small mobile display sizes. |
| Language hierarchy | Put English first and Simplified Chinese second for this project. Both languages must remain legible and pass the applicable contrast target. **English at least 1.2× the Chinese font size is an optional project design choice, not a sourced industry rule.** The source guidance does not prescribe a bilingual font-size ratio. Do not use color alone to convey language or meaning. |
| Lines and wrapping | Keep each language to at most two lines per cue in this project profile. Prefer one line when it fits. Break at punctuation or a syntactic boundary; do not split an article from its noun, a name, auxiliary/negation from its verb, or another closely linked phrase. Never wrap a token or truncate text to fit. If a cue does not fit, reflow into aligned phrase cues while preserving every word, or fail closed for human editorial correction. BBC and Netflix both recommend a two-line maximum for landscape/Netflix deliveries respectively; the project applies the limit to each language independently. |
| Background and outline | Use a tight backing behind the caption text only when required to preserve contrast over moving footage. A black backing with measured opacity and modest edge padding is an implementation option; verify actual rendered contrast rather than treating an opacity value as proof. A restrained outline/shadow may assist separation but is not a substitute for contrast checks. General M3 layouts must not use a background to hide source graphics. The Rose Garden exception below is narrowly scoped and disclosed. BBC says subtitles are commonly white on black and that background colours are no longer used in its own guidance; that is BBC practice, not a universal mandate. |
| Mobile behavior | Scale caption size and safe-area coordinates with the active picture, preserve line breaks and bilingual order, and keep the whole text inside the safe area after scaling. Check representative narrow mobile viewports and playback controls. For a baked-in video the viewer cannot resize the subtitle independently, so any clipping, illegibility, or overlay collision at the target mobile size is a release blocker. |

### Bilingual layout example

The line below is a formatting example only; it is not a transcript or
translation claim. Each language has a separate, centered text block. A real
cue may use one or two lines per language, but must remain within the safe area
and avoid all source graphics and important picture content.

```text
We will meet in the Rose Garden tomorrow.
我们明天将在玫瑰园会面。
```

An acceptable wrap preserves the phrase boundary and all words:

```text
We will meet in the Rose Garden
tomorrow.
我们明天将在玫瑰园
会面。
```

Do not force the second example if the line break separates a name or a
closely connected phrase. Reflow the cue at an aligned phrase boundary instead.

## Validation and exceptions

Before a video using this profile is called compliant with the **M3 project
profile**:

1. Confirm the active frame dimensions and verify the text bounding boxes stay
   inside the selected safe area; do not upscale a below-spec source to claim
   resolution compliance.
2. Verify cue text completeness, bilingual ordering, timings, line count,
   wrapping, and actual rendered glyph bounds. Automatic wrapping or
   truncation is a failure, not a successful fit.
3. Measure contrast on rendered frames. Inspect representative light, dark,
   and high-motion backgrounds and test the actual font fallback.
4. Inspect representative frames at cue boundaries, shot changes, source
   lower-thirds/graphics, and speaker close-ups. General M3 layouts must not
   obscure source graphics, mouths, faces, or important action. The Rose-only
   exception below may obscure only its human-verified source banner BBox.
5. Test playback in the target desktop and narrow-mobile layouts, including
   visible player controls. An automated geometry test is not a substitute for
   human visual review.
6. Keep ASR, translation, timing, source-frame, and visual review statuses
   pending until a human has checked the actual audio, wording, and rendered
   output. Record any exception and its owner decision; do not call an obscured
   or unreviewed source clean or approved.

If a source graphic occupies the normal subtitle position, the general M3
profile requires moving captions to another non-obstructing part of the frame
or splitting/re-timing the cue where linguistically sound. If no readable,
non-obstructing layout exists, preserve the original picture, document the
collision, and fail closed for owner review.

### Rose Garden source-banner masking exception

The user explicitly authorized a Rose Garden-specific opaque mask that fully
covers the source lower-third banner. This is a visual-treatment exception for
this event only; it does not change the general M3 no-overlap rule and is not
evidence that the source is clean or that any rights, event-match, lineage,
ASR, translation, or visual-review gate passed.

The renderer must require both the explicit Rose exception authorization and a
human-verified source-banner BBox at the probed source/output resolution. It
must not guess coordinates or substitute a full-width 30% band. The opaque
mask must be the source-banner BBox expanded outward by 1–5 output pixels on
each edge, with the source BBox, selected padding, resulting mask BBox, and
frame resolution recorded in the manifest. The current implementation choice
is 2 px per edge; this is an engineering choice within the authorized range,
not a value specified by the user's wording. Missing/unverified BBoxes,
invalid padding, a mask outside the frame, or overlap with any other protected
graphic must fail closed. The original source remains unchanged; the derivative
must be labelled `masked_not_clean`, and source-frame/visual review remains
pending. Text must still fit inside the narrow mask without covering unrelated
scene content.

At the time of this change, repository/workflow search did not locate a
separately authorized controlled cloud frame/BBox review path. This is a
`not found` search result, not proof that no such capability exists. Confirm an
authorized runner/reviewer route before extracting or inspecting source frames;
do not infer or fabricate a source banner BBox from event metadata or old probe
logs. Synthetic geometry fixtures are test data only and must never be used as
production render inputs.

The current production workflow therefore fails closed even if a dispatch
supplies review booleans and a syntactically complete frame-review record: no
trusted verifier for that controlled route exists yet. Before enabling a
production render, add a separately approved review mechanism that verifies
reviewer identity, timestamp, source timecode, actual source resolution, pixel
BBox, and its private evidence/approved-run reference. The rights, exact event
and timezone match, and YouTube-to-release lineage gates also require evidence
links and explicit completion; their current pending state blocks the workflow.
No evidence-provider responsibility is assigned by this profile.

## Rose Garden implementation status

The existing public Rose Garden MP4 was rendered by run
[38832525536](https://github.com/gdelt0003/gdelt0003/actions/runs/38832525536)
from `main` at `a696b18094b7629645df30d04251b069c695f2ef`; its manifest records
`layout_profile: default`, `caption_region_height_percent: null`, and
`visual_frame_review: required`. The video and subtitles are available in the
[public review prerelease](https://github.com/gdelt0003/gdelt0003/releases/tag/rose-garden-lunch-review)
and the [Rose Garden event page](https://gdelt0003.github.io/gdelt0003/events/rose-garden-lunch-2026-10-15/).
This proves the old review asset was published and is linked by the page; it
does not prove conformance to this profile or human visual/ASR/translation
review.

PR #50 is implementing a source-aware 68% caption layout and the opt-in,
source-banner-only Rose masking exception above. It remains unmerged and has
not been deployed. The prior public MP4 remains the old review asset; do not
replace it on the strength of a successful encode or manifest alone. A future
render may be labelled only as a public review draft while rights, event match,
URL-to-release lineage, ASR, translation, and human frame/visual review remain
pending.
