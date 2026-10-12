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
- The default-highlight job creates MP4 clips when YouTube permits the runner to download the source video. If YouTube requires sign-in, it deploys timestamped previews instead; configure the repository Actions secret `YOUTUBE_COOKIES` with an authorized Netscape-format cookies file to enable clip downloads.
