# gdelt0003 White House highlights

## Publish and download

- Three short MP4 highlights from the public White House video `oW-PQlgw1wo` are committed to `generated/clips/`, with metadata in `generated/default_batch.json`.
- GitHub Actions deploys the committed files to Pages, which plays them directly and provides an MP4 download link.
- To download the full `KroMEOZ8oFo` source, manually run the Pages workflow with `download_full_source` enabled. It uses yt-dlp with 50 concurrent fragments and publishes the MP4 as a GitHub Release asset, avoiding Git's 100 MiB per-file limit. The Pages page links directly to that asset.
- To attempt highlight regeneration, manually run the workflow with `regenerate_clips` enabled. If YouTube does not provide the source or both subtitle languages, generation fails and leaves the published clips unchanged.
