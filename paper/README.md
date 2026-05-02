# PolicyBench paper

This directory is the single manuscript source for the PolicyBench preprint.

Outputs:
- `app/public/paper/policybench.pdf` for arXiv / SSRN
- `app/public/paper/web/index.html` for the web-paper export
- copied static assets under `app/public/paper/` for `policybench.org/paper`

Suggested workflow:

1. Install app dependencies if `app/node_modules` is absent:

   ```bash
   cd app && bun install && cd ..
   ```

2. Render the manuscript:

   ```bash
   ./.venv/bin/python paper/render_paper.py
   ```

Notes:
- This scaffold assumes `quarto` and the app dependencies are installed
  separately. The renderer reads PolicyEngine design-system tokens from
  `app/node_modules/@policyengine/design-system/dist/tokens.css`.
- The manuscript tables read from `app/src/data.json`.
- Frozen manuscript inputs that need to be versioned live under
  `paper/snapshot/`. Keep that directory committed with the manuscript.
- `paper/render_paper.py` generates temporary figures internally, copies the
  retained PDF/web outputs into `app/public/paper/`, and removes temporary
  `paper/out/` and `paper/figures/` outputs before exiting. Those scratch
  directories are ignored; `app/public/paper/` is the served artifact set.
- The app route at `/paper` is a landing page for the manuscript and links to the rendered assets once they exist.
