import json
import os
import subprocess
import sys

youtube_url = os.environ.get('YOUTUBE_URL', 'https://www.youtube.com/@gdelt0003').strip()
limit = os.environ.get('VIDEO_LIMIT', '8').strip() or '8'
output_path = 'videos.json'

try:
    cmd = [
        'yt-dlp',
        '--flat-playlist',
        '--no-warnings',
        '--skip-download',
        '--print',
        '%(title)s|%(uploader)s|%(duration_string)s|%(webpage_url)s|%(thumbnail)s',
        '--playlist-end',
        limit,
        youtube_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'yt-dlp failed')
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    items = []
    for line in lines:
        parts = line.split('|')
        if len(parts) < 5:
            continue
        title, author, duration, url, thumbnail = parts[:5]
        items.append({
            'title': title,
            'author': author,
            'duration': duration,
            'url': url,
            'thumbnail': thumbnail,
        })
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
except Exception as exc:
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump([], fh, ensure_ascii=False, indent=2)
    print(f'Warning: {exc}', file=sys.stderr)
