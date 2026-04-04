# PolicyBench paper

This directory is the single manuscript source for the PolicyBench preprint.

Planned outputs:
- `paper/out/policybench.pdf` for arXiv / SSRN
- `paper/out/index.html` for the web-paper export
- copied static assets under `app/public/paper/` for `policybench.org/paper`

Suggested workflow:

1. Export frozen benchmark artifacts:

   ```bash
   ./.venv/bin/python scripts/export_paper_artifacts.py
   ```

2. Generate any derived paper assets:

   ```bash
   ./.venv/bin/python paper/generate_figures.py
   ```

3. Render the manuscript:

   ```bash
   ./.venv/bin/python paper/render_paper.py
   ```

Notes:
- This scaffold assumes `quarto` is installed separately.
- The app route at `/paper` is a landing page for the manuscript and links to the rendered assets once they exist.
