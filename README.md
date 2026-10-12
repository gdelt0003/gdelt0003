# gdelt0003 White House highlights

## Publish and regenerate

- Three short MP4 highlights from the public White House video `oW-PQlgw1wo` are committed to `generated/clips/`, with metadata in `generated/default_batch.json`.
- GitHub Actions deploys the committed files to Pages, which plays them directly and provides an MP4 download link.
- To attempt regeneration, manually run the workflow with `regenerate_clips` enabled. YouTube currently challenges GitHub-hosted runners to sign in, so regeneration can fail; the committed clips remain available and Pages still deploys them.
- The clips are 360p H.264/AAC segments selected from the shipyard announcement, submarine-production remarks, and Golden Fleet remarks.
