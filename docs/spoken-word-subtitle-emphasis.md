# Spoken-word subtitle emphasis

The full-video renderer can enlarge the currently spoken English word by 8%
vertically when it receives complete audio-derived word timings tied to the final
bilingual cues and an explicit soundtrack-review record. Without that evidence,
the renderer keeps its normal phrase-level English and Chinese captions.
The vertical-only scale keeps horizontal line width, wrapping, and caption
position stable, including the fixed Katie lower-third panel and its Chinese-
first ordering. It never estimates word positions from phrase duration or text
length.

Pass the JSON file with `--word-timings`. Its `cues` array must match the final
rendered cue order, 1-based cue indices, phrase start/end times, and English
text exactly. Every cue must include one timed entry for every whitespace-
separated English token, including punctuation attached to a token. Times are
absolute seconds in the source video timeline and must be finite, inside the
cue, ordered, non-overlapping, and representable at ASS centisecond precision
with at least three centiseconds per word.
The accepted `timing_source` values are `forced_alignment` and
`asr_word_timestamps`.

```json
{
  "schema_version": 1,
  "timing_source": "forced_alignment",
  "review": {
    "status": "verified",
    "checked_against_soundtrack": true,
    "evidence": "review/audio-pass.json"
  },
  "cues": [
    {
      "cue_index": 1,
      "start": 1.0,
      "end": 2.0,
      "english": "Hello, world.",
      "words": [
        {"text": "Hello,", "start": 1.1, "end": 1.4},
        {"text": "world.", "start": 1.5, "end": 1.9}
      ]
    }
  ]
}
```

The `review` fields are an explicit input attestation; the renderer does not
inspect the soundtrack or validate the evidence reference. Do not set them to
verified unless a reviewer actually checked the word timings against the
source audio. Passing `--disable-word-highlighting` records `disabled`;
otherwise missing, malformed, incomplete, out-of-order, or cue/text-misaligned
input records `not_verified` with a reason and leaves phrase captions intact.

For example, an operator may rerun the normal cloud processing command with
`--word-timings /path/to/reviewed-word-timings.json`. The status and reason are
included in the output manifest, quality checks, subtitle-export audit record,
and subtitle-burn audit record. Enabled captions retain fixed phrase cue
boundaries and the normal line wrapping. This feature has code-level tests
only; it has not been visually reviewed on rendered production footage.
