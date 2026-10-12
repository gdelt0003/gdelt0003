import json
import os
import subprocess
import sys


def parse_limit(raw_value):
    value = (raw_value or '8').strip()
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 8
    return max(1, parsed)


def normalize_video(entry):
    if not isinstance(entry, dict):
        return None

    title = (entry.get('title') or 'Untitled video').strip() or 'Untitled video'
    author = (entry.get('uploader') or entry.get('channel') or 'YouTube').strip() or 'YouTube'
    duration = entry.get('duration_string')
    url = (entry.get('webpage_url') or entry.get('url') or '').strip()
    thumbnail = (entry.get('thumbnail') or '').strip()

    if url and not (url.startswith('http://') or url.startswith('https://')):
        url = ''

    if not duration:
        seconds = entry.get('duration')
        if isinstance(seconds, int) and seconds >= 0:
            mins, secs = divmod(seconds, 60)
            hours, mins = divmod(mins, 60)
            if hours:
                duration = f'{hours}:{mins:02d}:{secs:02d}'
            else:
                duration = f'{mins}:{secs:02d}'
        else:
            duration = '—'

    return {
        'title': title,
        'author': author,
        'duration': duration,
        'url': url,
        'thumbnail': thumbnail,
    }


youtube_url = os.environ.get('YOUTUBE_URL', 'https://www.youtube.com/@gdelt0003').strip() or 'https://www.youtube.com/@gdelt0003'
limit = parse_limit(os.environ.get('VIDEO_LIMIT', '8'))
output_path = 'videos.json'
yt_dlp_bin = os.environ.get('YT_DLP_BIN', 'yt-dlp')

try:
    cmd = [
        yt_dlp_bin,
        '--flat-playlist',
        '--no-warnings',
        '--skip-download',
        '--dump-json',
        '--playlist-end',
        str(limit),
        youtube_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'yt-dlp failed')

    items = []
    for line in (ln.strip() for ln in result.stdout.splitlines() if ln.strip()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = normalize_video(payload)
        if item and item['url']:
            items.append(item)

    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
except Exception as exc:
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump([], fh, ensure_ascii=False, indent=2)
    print(f'Warning: {exc}', file=sys.stderr)
