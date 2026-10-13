---
name: bilingual-subtitle-verification
description: Verify bilingual English-Chinese video subtitles for transcript accuracy, translation fidelity, cue synchronization, readability, and the requested subtitle styling before release.
---

# Bilingual subtitle verification

Use this skill before publishing or replacing bilingual English-Chinese subtitles. A successful encode or a machine-generated manifest is not evidence that the translation is correct.

## Required verification passes

1. **Transcript and timing:** compare English captions with the event's original audio/video at the cited timestamps. Check names, numbers, negation, speaker changes, and sentence boundaries. Do not infer exact wording from a news article or an ASR transcript alone.
2. **Translation fidelity:** compare the Chinese to the verified English, preserving meaning, uncertainty, tone, and factual claims. For high-stakes or disputed lines, inspect the full sentence in context rather than scoring isolated ASR fragments.
3. **Independent comparison:** when model access is authorized, translate the complete sentence with at least ten distinct systems and blind-score a representative sample with at least three independent judges. Record the exact model IDs, sample method, score rubric, cost, disagreements, and adjudicated choice. Model consensus is evidence, not proof; resolve disagreements against the original audio and reliable event sources.
4. **Cue synchronization:** inspect representative beginnings, middle, and ending points, plus every flagged cue. Confirm English and Chinese appear together for the same phrase, do not overlap neighboring cues, and do not split a phrase into semantically unrelated fragments. Cue-level timing is not word-level forced alignment; state that limitation.
5. **Readability and styling:** verify that English is at least 20% larger than Chinese, both language lines remain within the safe width, each language wraps to at most two lines, and captions do not cover persistent lower-thirds or essential scene content. Review actual rendered frames from the cloud runner, not only subtitle source files.
6. **Rendered output and deployment:** on the cloud runner, check source/output duration and resolution, audio presence, encode errors, VTT/SRT cue integrity, and the deployed URLs. Verify the deployed VTT corresponds to the video asset that was just rendered.

## Release report

Record each check as `passed`, `failed`, or `not_verified`; attach timestamped examples and cite the source used. A failed synchronization, missing-language, overlap, resolution, style-contract, or render check blocks release. Translation accuracy must remain `not_verified` until the source-audio review and independent comparison are actually completed. Never turn a missing credential, inaccessible source, or uninspected frame into a passing result.

Use GitHub Actions/cloud runners for video downloads, frame extraction, probing, and encoding when requested. Do not silently fall back to local video files or local video processing.
