# gdelt0003 White House highlights

## Publish and download

- Three short MP4 highlights from the public White House video `oW-PQlgw1wo` are committed to `generated/clips/`, with metadata in `generated/default_batch.json`.
- GitHub Actions deploys the committed files to Pages, which plays them directly and provides an MP4 download link.
- The full `KroMEOZ8oFo` download can be attempted by manually running the Pages workflow with `download_full_source` enabled. The job uses yt-dlp with 50 concurrent fragments and publishes a complete MP4 as a GitHub Release asset; it never publishes partial downloads.
- YouTube challenged Ubuntu, Windows, and macOS GitHub-hosted runners to sign in before returning a video format. No full-source Release asset exists, and the current Pages clips remain the older low-resolution batch.
- To attempt highlight regeneration, manually run the workflow with `regenerate_clips` enabled. If YouTube does not provide the source or both subtitle languages, generation fails and leaves the published clips unchanged.
