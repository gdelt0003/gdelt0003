# gdelt0003
A small GitHub Pages repo that fetches latest YouTube videos via GitHub Actions and publishes them to Pages.

## Quick start

1. Create or update the repository variable `YOUTUBE_URL` to a target YouTube URL such as:
   - `https://www.youtube.com/@gdelt0003`
   - `https://www.youtube.com/playlist?list=...`
2. Optionally set `VIDEO_LIMIT` (default: `8`).
3. Push to `main` or run the workflow manually.
4. GitHub Pages will publish the site automatically.

## Notes

- No local frontend install is required.
- The workflow runs in GitHub Actions, installs `yt-dlp`, fetches data, and deploys the static site.
- For production, replace the example YouTube URL with your real channel or playlist.
