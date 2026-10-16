---
name: multi-source-event-video-production
description: Research White House public-event recordings by event identity, produce reviewed bilingual clip variants, and publish evidence-led event pages.
---

# Multi-source event video production

Use this skill for public-event source discovery, bilingual video production, multi-style editing, and scheduled Pages publication.

## Event isolation

1. Create one event record per real event using the event date (not upload date), local time and precision/timezone when established, location, event type/title, and participants. Do not assign an event key while required identity evidence is missing.
2. Start each event's source group from its own official White House reference when available. Never treat another event/date as an alternative because it has a similar topic or speaker.
3. Search for additional same-event publishers, but keep search results marked as leads until the source page and relevant moving frames/audio have been inspected. Record direct URL, publisher, publication metadata, runtime, video-stream resolution (not thumbnail size), matched event timestamp, frame graphics, source lineage, and unresolved rights.
4. Distinguish event time from upload time, player controls/CC from graphics embedded in the video, and same-source syndication from an independent camera.
5. Do not describe a candidate as clean, same-time, a different angle, or continuous unless direct frame/audio evidence supports that label. Preserve footage in-frame graphics; do not erase or crop them to claim a clean source.
6. Keep real camera locations, uncertainty, distance, azimuth, height, pitch, and source evidence separate. Leave the map unavailable where measurements are not public and reliable.

## Production controls

1. Run downloads, metadata probing, frame checks, ASR, subtitle rendering, and video encoding only on an authorized GitHub-hosted runner. Do not process video from a developer workstation.
2. Record the event identity, selected source URL, source/event match evidence, and rights status accurately, including unknown or unreviewed values. Do not make private processing conditional on HTTPS evidence links, operator checkboxes, or other workflow-added attestations unless a separately identified legal, platform, contract, or user requirement applies. Never claim that rights or event matching were confirmed when they were not. Before public release, follow applicable legal and platform requirements and complete the actual source/event, frame, ASR, translation, and rights reviews; an internal checklist or evidence URL is not itself proof of permission. A non-anchor source must be identified as a reviewed same-event source before it is presented as verified.
3. Reject source streams below 1920x1080 rather than upscaling. Preserve the original frame, duration context, and source graphics.
4. Produce English ASR and Simplified Chinese translation, but identify ASR/MT as unreviewed until a human checks the actual source audio, names, numbers, negation, and meaning. Do not call heuristic timing word-aligned.
5. Animate or emphasize a currently spoken English word only when word timestamps come from an audio alignment/ASR process and have been checked against the soundtrack. If that evidence is unavailable, render normal readable captions and mark word highlighting unverified.
6. Generate ten distinct documented edit presets from reviewed, reasoned highlight intervals. Each result must retain source time range, event ID, source attribution, style name, subtitle files, and review state. "Viral" describes an editorial aim, not a guaranteed result.
7. Keep source audio as recorded by default. Do not clone or impersonate a person's voice without documented authorization and appropriate consent; never synthesize a public figure saying words not present in the recording.
8. Store candidate/source evidence in the event workbook with explicit unverified values. Do not copy video binaries into the git tree by default.
9. Scheduled discovery may publish new source leads, not automatically publish video. Keep event identity, source-match, and rights review states explicit; do not turn an unknown or pending status into a claim of verification.
10. Deploy the static, responsive Pages site only from a successful workflow. Keep videos, transcript downloads, source links, and event evidence grouped by event, and label machine translation and unresolved quality checks.
11. Maintain discovery sources in the workbook's editable `Source Directory` sheet. Preserve user-provided URLs and the user's own source annotations without attributing them to another person. A configured source is not automatically a working collector: label unconnected sources as manual-review only and record each actual attempt with its run link.
12. Leave actual attendance duration, speech word count (including language and counting method), and topic claims blank unless supported by direct/source-backed evidence. Never infer these metrics from publisher upload timestamps, prediction-market activity, or video runtime.

## Release checklist

- [ ] A unique, evidence-backed event identity is present; unknown date/time is not inferred from upload metadata.
- [ ] Candidate sources belong to the same event; matching time and camera/continuity claims have direct evidence.
- [ ] Rights status, actual video resolution, source graphics, and review status are recorded accurately; unresolved status is not represented as permission or approval.
- [ ] Highlight ranges are valid and each has an editorial reason.
- [ ] Ten named edit presets are distinct and the manifest names each output.
- [ ] English transcript and Chinese translation are available, with unresolved review status visible.
- [ ] Any active spoken-word effect has audio-derived word timing; otherwise it is not advertised as synchronized.
- [ ] Original source frame/audio is not represented as clean if it includes embedded logos, banners, or tickers.
- [ ] Generated files and event workbook are linked from the event-specific Pages view.
- [ ] Scheduled source discovery is provenance-labelled and cannot silently promote leads to verified sources.
- [ ] Editable source registrations retain URLs, user annotations, collection mode, last result, and run evidence; unsupported source collectors are not represented as active.
- [ ] Actual attendance minutes, spoken word count, and topics are cited or left unknown.
- [ ] No unapproved paid API or voice-cloning request was made.
