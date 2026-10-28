# Activate GitHub Pages for RL Overlay Studio

The **Beta 8.46 gallery has been committed** to `docs/showcase.html` with 43 static media fragments, but GitHub Pages is currently **not enabled** on this repository.

The deployment workflow failed with the official GitHub message:

> Get Pages site failed (Not Found); Create Pages site failed (Resource not accessible by integration).

This is a repository setting/permissions issue, not an error in the gallery's HTML.

## Enable once in GitHub

1. Sign in to GitHub as the repository owner.
2. Go to **Lukiseven/RL-Overlay-Studio → Settings → Pages**.
3. Under **Build and deployment → Source**, select **GitHub Actions** (not Deploy from a branch).
4. Save.
5. Go to **Actions → Deploy GitHub Pages Gallery → Run workflow**, select `main`, then run.
6. When the workflow succeeds, open `https://lukiseven.github.io/RL-Overlay-Studio/` or `https://lukiseven.github.io/RL-Overlay-Studio/showcase.html`.

The Pages workflow is `.github/workflows/pages-showcase.yml` and automatically deploys on future `docs/**` changes.

### Content

The client-side gallery contains 46 PNG previews and 12 animated WebP sequences from the actual Beta 8.46 Chromium output. The source for the private overlay templates, API credentials and private backend is not published. The Windows app and Dock snapshots represent HTML transcriptions of the PyQt6 application structure, not native app screenshots.

### If GitHub Pages remains unavailable

Use the downloadable standalone file `RL_Overlay_Studio_Beta_8.46_DEMO_AUTONOME.html`. This includes all media in one file and does not require a server or assets folder. The multi-file ZIP works with a standard static HTTP server such as `python -m http.server 8000` opened at `http://localhost:8000`.
