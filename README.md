# gdelt0003 White House highlights

## Generate and deploy

- GitHub Actions downloads and cuts three short MP4 highlights from the public White House video `oW-PQlgw1wo`.
- Generated MP4 files and their manifest are committed to `generated/clips/` and `generated/default_batch.json`.
- GitHub Pages plays the stored clips directly and provides an MP4 download link.
- The clips are 360p H.264/AAC segments selected from the shipyard announcement, submarine-production remarks, and Golden Fleet remarks.
