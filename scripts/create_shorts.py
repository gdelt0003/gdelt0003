"""Create bilingual vertical shorts from a long YouTube video."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_URL = "https://www.youtube.com/watch?v=oW-PQlgw1wo"
OUTPUT_ROOT = Path("outputs")
VIDEO_FILTER = (
    "bestvideo[height>=1080]+bestaudio/"
    "best[height>=1080]/bestvideo+bestaudio/best"
)
HIGHLIGHTS = (
    {
        "id": "arsenal-production",
        "start": 723.2,
        "end": 779.0,
        "title": "Arsenal 2: 9 million production hours",
    },
    {
        "id": "navy-threats",
        "start": 1258.4,
        "end": 1304.8,
        "title": "A new shipyard and the future Navy",
    },
    {
        "id": "eight-wars",
        "start": 2517.1,
        "end": 2536.8,
        "title": "Trump on the Russia-Ukraine war",
    },
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        details = result.stderr.strip() if capture and result.stderr else ""
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{details}" if details else "")
        )
    return result.stdout if capture else ""


def timestamp_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_vtt(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", content)
    cues: list[Cue] = []
    timing = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+"
        r"(\d{2}:\d{2}:\d{2}\.\d{3})"
    )
    for block in blocks:
        match = timing.search(block)
        if not match:
            continue
        lines = [
            re.sub(r"<[^>]+>", "", line)
            for line in block.splitlines()[1:]
            if "-->" not in line and not line.startswith("NOTE")
        ]
        text = " ".join(html.unescape(" ".join(lines)).split())
        text = text.replace("\u200b", "").strip()
        if text:
            cues.append(
                Cue(
                    timestamp_seconds(match.group(1)),
                    timestamp_seconds(match.group(2)),
                    text,
                )
            )
    return sorted(cues, key=lambda cue: (cue.start, cue.end))


def remove_rolling_overlap(cues: list[Cue]) -> list[Cue]:
    cleaned: list[Cue] = []
    for cue in cues:
        text = normalize_transcript_text(cue.text)
        if cleaned and cue.start - cleaned[-1].start <= 5:
            previous_words = cleaned[-1].text.split()
            current_words = text.split()
            if (
                len(current_words) == 1
                and previous_words
                and previous_words[-1].strip(".,!?").casefold()
                == current_words[0].strip(".,!?").casefold()
            ):
                continue
            overlap = 0
            for length in range(min(len(previous_words), len(current_words)), 1, -1):
                if [word.casefold() for word in previous_words[-length:]] == [
                    word.casefold() for word in current_words[:length]
                ]:
                    overlap = length
                    break
            if overlap:
                text = " ".join(current_words[overlap:])
            if not text:
                continue
        cleaned.append(Cue(cue.start, cue.end, text))
    return cleaned


def normalize_transcript_text(text: str) -> str:
    return text.replace(
        "More holes through our prime yards",
        "More hulls through our prime yards",
    ).replace(
        "holes through our prime yards",
        "hulls through our prime yards",
    ).replace(
        "our sailors marines",
        "our sailors and Marines",
    )


def translate(text: str, cache: dict[str, str]) -> str:
    reviewed_translations = {
        "arsenal 2 will help us attack production bottlenecks with the footprint to add up to 9 million production hours per year into our submarine supply chain.": "Arsenal 2 将帮助我们突破生产瓶颈，预计每年可为潜艇供应链新增 900 万工时。",
        "we're delivering systems that will hunt threats before the crews can even see them.": "我们正在交付能够在舰员察觉威胁之前就将其锁定的系统。",
        "we'll strike adversaries before they can react.": "我们将在对手反应之前发动打击。",
        "we'll bring the war fighters home safely to their families.": "我们将让作战人员平安回家，与家人团聚。",
        "that's a 15% surge in total capacity.": "这使总产能提升 15%。",
        "this is not a smaller business for our ship builders.": "这不是在缩减造船业务，而是要扩大规模。",
        "it is a larger one.": "我们的造船业务只会扩大。",
        "more hulls through our prime yards at better margin, improving with every boat as our workforce gets faster at the same work that drives up our rate and ensures we meet and eventually exceed 1 plus two.": "我们的主要造船厂将以更高利润率建造更多舰艇。随着每艘艇的生产流程日益熟练、效率不断提升，我们会提高产量，确保达到并最终超过“1+2”的目标。",
        "we ended eight wars.": "我们结束了八场战争。",
        "i ended eight wars.": "我结束了八场战争。",
        "we haven't ended russia ukraine yet.": "俄乌战争还没有结束。",
        "i'm working on that one.": "我正在推动解决这场战争。",
        "that one i thought would be the easiest one for me.": "我原以为这是最容易解决的一场。",
        "but we've ended eight wars and that's going to happen too pretty soon.": "我们已经结束了八场战争；这场战争也会很快结束。",
        "a lot of people dying in that war.": "那场战争中仍有很多人丧生。",
        "it's ridiculous.": "这令人难以接受。",
        "it's ridiculous what's happened, but it's, believe it or not, doesn't look it, but it's actually getting closer.": "发生的一切令人难以接受；但信不信由你，局势实际上正越来越接近解决。",
        "that is how we're strengthening the navy.": "这正是我们强化海军的方式。",
        "that is how we take care of our sailors and marines.": "这正是我们守护水兵和海军陆战队员的方式。",
        "that is how we advance 21st century ship building and that is how we defend the american homeland.": "这正是我们推动21世纪造船业发展、保卫美国本土的方式。",
        "to our allies around the globe, arsenal 2 sends us a message of unbreakable american commitment.": "面向全球盟友，Arsenal 2 的建设传递出美国坚定不移的承诺。",
        "to our adversaries, let this groundbreaking be a clearest message to you.": "面向对手，这次开工典礼释放出最明确的信号。",
        "american technological machine is fully awake, fully armed, and ready to fight.": "美国的科技实力已全面就位、全副武装，随时准备战斗。",
        "you can run, but you'll only die tired.": "你可以逃跑，但最终只会筋疲力尽。",
        "but you know what?": "但你知道吗？",
        "if you piss us off, we're going to sneak into your country in the middle of night and snatch you and your wife while you sleep in your beds.": "如果你激怒我们，我们会在深夜潜入你的国家，在你们熟睡时把你和你的妻子带走。",
    }
    reviewed = reviewed_translations.get(text.casefold())
    if reviewed:
        cache[text] = reviewed
        return reviewed
    if text in cache:
        return cache[text]
    if not text.strip():
        return ""

    query = urllib.parse.urlencode({"q": text, "langpair": "en|zh-CN"})
    request = urllib.request.Request(
        f"https://api.mymemory.translated.net/get?{query}",
        headers={"User-Agent": "gdelt0003-shorts/1.0"},
    )
    error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            if result.get("responseStatus") != 200:
                raise RuntimeError(
                    f"Translation service returned status {result.get('responseStatus')}"
                )
            translated = html.unescape(
                result["responseData"]["translatedText"]
            ).strip()
            if not translated:
                raise RuntimeError("Translation service returned an empty translation")
            translated = improve_translation(translated)
            cache[text] = translated
            time.sleep(0.15)
            return translated
        except Exception as exc:  # Retry transient service/network errors.
            error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Unable to translate subtitle {text!r}: {error}")


def improve_translation(text: str) -> str:
    replacements = {
        "阿森纳 2": "Arsenal 2",
        "阿森纳2": "Arsenal 2",
        "军火库 2": "Arsenal 2",
        "军火库2": "Arsenal 2",
        "生产小时": "生产工时",
        "攻击生产": "解决生产",
        "问题集": "当前难题",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text


def ass_time(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def subtitle_text(cues: list[Cue], start: float, end: float, cache: dict[str, str]):
    fragments = []
    spans = []
    for cue in cues:
        cue_start = max(cue.start, start)
        cue_end = min(cue.end, end)
        if cue_start >= cue_end or cue.end <= start or cue.start >= end:
            continue
        if fragments:
            fragments.append(" ")
        text_start = sum(map(len, fragments))
        fragments.append(cue.text)
        spans.append((text_start, text_start + len(cue.text), cue_start - start, cue_end - start))

    transcript = "".join(fragments)
    selected = []
    sentence_pattern = re.compile(r"\S.*?(?:[.!?]+(?=\s|$)|$)", re.DOTALL)
    for match in sentence_pattern.finditer(transcript):
        english = match.group().strip()
        if not english:
            continue
        sentence_spans = []
        for text_start, text_end, cue_start, cue_end in spans:
            overlap_start = max(text_start, match.start())
            overlap_end = min(text_end, match.end())
            if overlap_start >= overlap_end:
                continue
            span_width = max(1, text_end - text_start)
            time_width = cue_end - cue_start
            sentence_spans.append(
                (
                    cue_start + (overlap_start - text_start) / span_width * time_width,
                    cue_start + (overlap_end - text_start) / span_width * time_width,
                )
            )
        if not sentence_spans:
            continue
        cue_start = min(span[0] for span in sentence_spans)
        cue_end = max(span[1] for span in sentence_spans)
        if cue_end - cue_start < 0.5:
            continue
        chinese = translate(english, cache)
        selected.append(
            {
                "start": cue_start,
                "end": cue_end,
                "english": "\n".join(textwrap.wrap(english, width=48)),
                "chinese": "\n".join(textwrap.wrap(chinese, width=24)),
            }
        )
    for current, following in zip(selected, selected[1:]):
        if current["end"] > following["start"]:
            current["end"] = max(
                current["start"] + 0.25, following["start"]
            )
    selected = [cue for cue in selected if cue["end"] - cue["start"] >= 0.5]
    return selected


def load_translation_cache(path: Path, output_dir: Path) -> dict[str, str]:
    cache: dict[str, str] = {}
    if path.is_file():
        cache.update(json.loads(path.read_text(encoding="utf-8")))
    for subtitle_path in output_dir.glob("*.en-zh.srt"):
        for block in re.split(r"\n\s*\n", subtitle_path.read_text(encoding="utf-8-sig")):
            lines = block.splitlines()
            if len(lines) >= 4:
                cache.setdefault(lines[2], lines[3])
    return cache


def write_ass(path: Path, cues: list[dict], style: str, title: str):
    if style == "punchy":
        style_line = (
            "Style: Default,Arial,45,&H00FFFFFF,&H0000D7FF,&H00101010,"
            "&HBE000000,-1,0,0,0,100,100,0,0,1,5,1,2,75,75,170,1"
        )
        title_color = r"{\1c&H0000D7FF&\b1}"
    else:
        style_line = (
            "Style: Default,Arial,36,&H00FFFFFF,&H0000D7FF,&H00101010,"
            "&H96000000,0,0,0,0,100,100,0,0,1,3,1,2,75,75,115,1"
        )
        title_color = r"{\1c&H0000D7FF&\b1}"

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        "Dialogue: 2,0:00:00.00,9:59:59.99,Default,,75,75,90,,"
        r"{\an8\pos(540,80)\fs28\b1\1c&H00D5FFF3&\bord1}"
        "WHITE HOUSE OFFICIAL VIDEO  |  OCTOBER 6, 2026",
        f"Dialogue: 1,0:00:00.00,0:00:04.00,Default,,75,75,95,,"
        f"{{\\an8\\pos(540,145)\\fs44}}{title_color}{ass_escape(title)}",
    ]
    for cue in cues:
        english = ass_escape(cue["english"]).replace("\n", r"\N")
        chinese = ass_escape(cue["chinese"]).replace("\n", r"\N")
        if style == "punchy":
            text = r"{\b1}" + english + r"\N{\1c&H0000D7FF&\b1}" + chinese
        else:
            text = english + r"\N{\1c&H0000D7FF&}" + chinese
        lines.append(
            f"Dialogue: 0,{ass_time(cue['start'])},{ass_time(cue['end'])},"
            f"Default,,75,75,100,,{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def filter_for(style: str, ass_path: Path) -> str:
    ass_path_text = ass_path.resolve().as_posix().replace(":", r"\:")
    subtitles = f"subtitles='{ass_path_text}':fontsdir='C\\:/Windows/Fonts'"
    if style == "punchy":
        return (
            "split=2[bg][fg];"
            "[bg]scale=540:960:force_original_aspect_ratio=increase,"
            "crop=540:960,boxblur=12:6,eq=saturation=1.25:contrast=1.06,"
            "scale=1080:1920:flags=bicubic[background];"
            "[fg]crop=iw:ih*0.76:0:0,scale=1166:-2:flags=lanczos,"
            "crop=1080:ih:(iw-1080)/2:0[foreground];"
            "[background][foreground]overlay=0:(H-h)/2-80,"
            f"{subtitles}"
        )
    return (
        "split=2[bg][fg];"
        "[bg]scale=540:960:force_original_aspect_ratio=increase,"
        "crop=540:960,boxblur=12:6,eq=saturation=0.82,"
        "scale=1080:1920:flags=bicubic[background];"
        "[fg]crop=iw:ih*0.76:0:0,scale=1080:-2:flags=lanczos[foreground];"
        "[background][foreground]overlay=(W-w)/2:(H-h)/2-80,"
        f"{subtitles}"
    )


def video_duration(ffprobe: str, path: Path) -> float:
    data = json.loads(
        run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture=True,
        )
    )
    return float(data["format"]["duration"])


def video_dimensions(ffprobe: str, path: Path) -> tuple[int, int]:
    data = json.loads(
        run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            capture=True,
        )
    )
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create 1080x1920 bilingual short variants from a long video."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="YouTube video URL")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT / "whitehouse-oct-06-2026")
    parser.add_argument("--yt-dlp", default=os.environ.get("YT_DLP_BIN", "yt-dlp"))
    parser.add_argument("--ffmpeg", default=os.environ.get("FFMPEG_BIN", "ffmpeg"))
    parser.add_argument("--ffprobe", default=os.environ.get("FFPROBE_BIN", "ffprobe"))
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep downloaded source segments in the output directory.",
    )
    args = parser.parse_args()

    if shutil.which(args.yt_dlp) is None and not Path(args.yt_dlp).is_file():
        parser.error(f"yt-dlp executable not found: {args.yt_dlp}")
    if shutil.which(args.ffmpeg) is None and not Path(args.ffmpeg).is_file():
        parser.error(f"ffmpeg executable not found: {args.ffmpeg}")
    if shutil.which(args.ffprobe) is None and not Path(args.ffprobe).is_file():
        parser.error(f"ffprobe executable not found: {args.ffprobe}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = args.output_dir / "source"
    source_dir.mkdir(exist_ok=True)
    metadata_path = source_dir / "metadata.json"
    metadata = json.loads(run([args.yt_dlp, "-J", "--no-warnings", args.url], capture=True))
    if metadata.get("duration", 0) <= 1800:
        raise RuntimeError("Source video must be longer than 30 minutes.")
    metadata_path.write_text(
        json.dumps(
            {
                "id": metadata.get("id"),
                "title": metadata.get("title"),
                "uploader": metadata.get("uploader"),
                "upload_date": metadata.get("upload_date"),
                "duration_seconds": metadata.get("duration"),
                "url": metadata.get("webpage_url"),
                "source_caption": "YouTube English auto captions",
                "translation": "MyMemory English-to-Simplified-Chinese machine translation",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    captions_path = source_dir / f"{metadata['id']}.en.vtt"
    run(
        [
            args.yt_dlp,
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en",
            "--sub-format",
            "vtt",
            "--sleep-subtitles",
            "2",
            "--output",
            str(source_dir / "%(id)s.%(ext)s"),
            args.url,
        ]
    )
    if not captions_path.is_file():
        raise RuntimeError(f"English caption track was not downloaded: {captions_path}")
    cues = remove_rolling_overlap(parse_vtt(captions_path))
    if not cues:
        raise RuntimeError("Downloaded caption track did not contain readable cues.")

    translation_cache_path = source_dir / "translations.json"
    translation_cache = load_translation_cache(
        translation_cache_path, args.output_dir
    )
    manifest = {
        "source": {
            "title": metadata.get("title"),
            "url": metadata.get("webpage_url"),
            "upload_date": metadata.get("upload_date"),
            "duration_seconds": metadata.get("duration"),
        },
        "asr": "YouTube English auto-generated captions; review names and numbers.",
        "translation": "Machine translation (MyMemory, en -> zh-CN); review before publishing.",
        "output": {"width": 1080, "height": 1920, "fps": 30},
        "highlights": [],
    }

    for highlight in HIGHLIGHTS:
        if highlight["end"] > metadata["duration"]:
            raise RuntimeError(f"Highlight exceeds source duration: {highlight['id']}")
        clip_id = highlight["id"]
        source_clip = source_dir / f"{clip_id}.mp4"
        run(
            [
                args.yt_dlp,
                "--no-warnings",
                "--download-sections",
                f"*{highlight['start']}-{highlight['end']}",
                "--force-keyframes-at-cuts",
                "--merge-output-format",
                "mp4",
                "-f",
                VIDEO_FILTER,
                "-o",
                str(source_clip),
                args.url,
            ]
        )
        if not source_clip.is_file():
            raise RuntimeError(f"Source clip was not created: {source_clip}")

        clip_cues = subtitle_text(
            cues, highlight["start"], highlight["end"], translation_cache
        )
        if not clip_cues:
            raise RuntimeError(f"No English caption cues found for {clip_id}")
        clip_manifest = {
            **highlight,
            "source_start": highlight["start"],
            "source_end": highlight["end"],
            "source_video": metadata.get("webpage_url"),
            "subtitles": f"{clip_id}.en-zh.srt",
            "variants": [],
        }
        srt_lines = []
        for index, cue in enumerate(clip_cues, start=1):
            srt_lines.extend(
                [
                    str(index),
                    f"{srt_time(cue['start'])} --> {srt_time(cue['end'])}",
                    cue["english"],
                    cue["chinese"],
                    "",
                ]
            )
        (args.output_dir / f"{clip_id}.en-zh.srt").write_text(
            "\n".join(srt_lines), encoding="utf-8-sig"
        )
        translation_cache_path.write_text(
            json.dumps(translation_cache, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for style in ("editorial", "punchy"):
            ass_path = source_dir / f"{clip_id}.{style}.ass"
            write_ass(ass_path, clip_cues, style, highlight["title"])
            output_path = args.output_dir / f"{clip_id}-{style}.mp4"
            run(
                [
                    args.ffmpeg,
                    "-y",
                    "-i",
                    str(source_clip),
                    "-vf",
                    filter_for(style, ass_path),
                    "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ]
            )
            actual_duration = video_duration(args.ffprobe, output_path)
            width, height = video_dimensions(args.ffprobe, output_path)
            expected_duration = highlight["end"] - highlight["start"]
            if (width, height) != (1080, 1920):
                raise RuntimeError(
                    f"Unexpected output resolution for {output_path.name}: "
                    f"{width}x{height}"
                )
            if abs(actual_duration - expected_duration) > 3:
                raise RuntimeError(
                    f"Unexpected duration for {output_path.name}: "
                    f"{actual_duration:.1f}s (expected {expected_duration:.1f}s)"
                )
            clip_manifest["variants"].append(
                {
                    "style": style,
                    "file": output_path.name,
                    "duration_seconds": round(actual_duration, 2),
                    "resolution": f"{width}x{height}",
                }
            )
            print(f"Created {output_path} ({actual_duration:.1f}s)")
        manifest["highlights"].append(clip_manifest)
        if not args.keep_source:
            source_clip.unlink()
            for style in ("editorial", "punchy"):
                (source_dir / f"{clip_id}.{style}.ass").unlink(
                    missing_ok=True
                )

    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


def srt_time(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},"
        f"{milliseconds:03d}"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
