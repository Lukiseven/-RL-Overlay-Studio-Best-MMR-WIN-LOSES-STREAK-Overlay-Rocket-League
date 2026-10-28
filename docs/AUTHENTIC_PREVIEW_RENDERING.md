# Authentic preview rendering — Beta 8.46

The previous presentation mockups used manually redrawn SVG artwork. Those images
were **not faithful to the actual application** and must not be described as real screenshots.

## Private input

Use the actual, privately held \`RL_Overlay_Studio_Beta_8.46_Presentation_Reelle.html\` file. 
It embeds the original overlay HTML/CSS/JS, the presentation states and rank imagery,
and a Python/PyQt-based HTML transcription of the five desktop pages and Dock.

**Do not commit this source HTML, embedded templates, original logos/assets, fonts,
Discord IDs, tokens or private API implementation to the public audit repository.**

## Regenerate locally

\`\`\`bash
python -m pip install playwright pillow
python -m playwright install chromium

python tools/render_beta846_previews.py \
  --source "/local/private/RL_Overlay_Studio_Beta_8.46_Presentation_Reelle.html" \
  --output preview_export
\`\`\`

For system-installed Chromium, add \`--chromium /usr/bin/chromium\`.

The renderer uses a **new Chromium JS context for each overlay state**, avoiding
the incorrect result where every mode rendered the same classic banner.

## Outputs

- Four main overlays from original embedded HTML/CSS/JS
- Rank/MMR/Top Rank, streak, rank change and popup states
- Players MMR, left/right and departures
- Showmatch and winner states
- Five main application pages from the source-based UI transcription
- Source-based In-Game Dock categories and Premium states

Every PNG is rendered with alpha transparency outside the designed UI component.
Do not remove a screenshot background by AI matting or alter the UI artwork.

The native desktop and native in-game Qt windows are **not** executable on this
Linux rendering environment. Their captures are explicitly source-backed HTML
transcriptions, not native Windows screenshots.

## Publishing

Before replacing the existing previews in \`media/previews\` and \`docs/assets\`,
review the exported images visually and verify their dimensions and alpha channel.
Only flattened **PNG previews**, not the private render source file, may be published.

This repository is an intentionally incomplete audit source, not an open-source
rebuild of the production app.
