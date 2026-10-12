import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NASA_ID = "20230830_OSIRIS_Briefing_hbr"
NASA_TITLE = "Press Conference - OSIRIS-REx Sample Return"
NASA_BASE = f"https://images-assets.nasa.gov/video/{NASA_ID}"
NASA_SOURCE = f"{NASA_BASE}/{NASA_ID}~mobile.mp4"
NASA_PAGE = f"https://images.nasa.gov/details/{NASA_ID}"
OUTPUT = Path("generated")
CLIPS = [
    {
        "id": "nasa-osiris-liftoff",
        "title": "Countdown and OSIRIS-REx liftoff",
        "start": 0,
        "end": 45,
        "note": "Opening launch sequence and countdown from the NASA briefing.",
    },
    {
        "id": "nasa-bennu-origin-of-life",
        "title": "Could Bennu samples explain the origin of life?",
        "start": 1460,
        "end": 1525,
        "note": "Science discussion of Bennu, organic material, and the origin-of-life question.",
    },
    {
        "id": "nasa-bennu-unexpected-discovery",
        "title": "What surprised the team about Bennu?",
        "start": 2280,
        "end": 2340,
        "note": "A discussion of unexpected findings in the returned asteroid material.",
    },
]


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return result


def download_source(destination):
    request = urllib.request.Request(
        NASA_SOURCE,
        headers={"User-Agent": "gdelt0003-pages-highlight-generator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clip_dir = OUTPUT / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    with tempfile.TemporaryDirectory(prefix="nasa-highlights-") as tmp:
        source = Path(tmp) / "nasa-source.mp4"
        print(f"Downloading public NASA source: {NASA_PAGE}")
        download_source(source)

        for clip in CLIPS:
            filename = f"{clip['id']}.mp4"
            destination = clip_dir / filename
            run([
                "ffmpeg", "-y", "-ss", str(clip["start"]),
                "-t", str(clip["end"] - clip["start"]), "-i", str(source),
                "-vf", "scale='min(720,iw)':-2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                str(destination),
            ])
            if not destination.exists() or destination.stat().st_size == 0:
                raise RuntimeError(f"ffmpeg did not create a valid clip: {destination}")
            generated.append({
                "id": clip["id"],
                "title": clip["title"],
                "start_sec": clip["start"],
                "end_sec": clip["end"],
                "duration_sec": clip["end"] - clip["start"],
                "status": "ready",
                "source_channel": "NASA",
                "source_title": NASA_TITLE,
                "source_url": NASA_PAGE,
                "file": f"generated/clips/{filename}",
                "file_size_bytes": destination.stat().st_size,
                "note": clip["note"],
            })
            print(f"Generated {destination} ({destination.stat().st_size} bytes)")

    manifest = {
        "status": "ready",
        "message": "Three real MP4 highlight clips were generated from NASA public media by GitHub Actions.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": NASA_PAGE,
        "source_attribution": "NASA Image and Video Library",
        "batch": generated,
    }
    (OUTPUT / "default_batch.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error generating default highlight clips: {error}", file=sys.stderr)
        raise SystemExit(1)
