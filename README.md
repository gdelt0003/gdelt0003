# gdelt0003 Pages highlights

GitHub Actions cuts and saves three MP4 highlight examples from a public, 59-minute NASA Image and Video Library briefing. The Pages site loads the committed manifest and plays the actual generated clips.

## Generate and deploy

- Push to `main` to generate the default batch and deploy Pages.
- Run **Generate default highlights and deploy Pages** manually to regenerate it.
- Generated clips and their manifest are committed under `generated/`.

The public NASA source is used because YouTube may require sign-in verification for downloads from GitHub-hosted Actions runners. Clip timestamps target the briefing's opening liftoff sequence, origin-of-life discussion, and unexpected Bennu findings. The page links to the original source.
