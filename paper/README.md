# PolicyBench paper

This directory is the single manuscript source for the PolicyBench preprint.

Outputs:
- `app/public/paper/policybench.pdf` for arXiv / SSRN
- `app/public/paper/web/index.html` for the web-paper export
- copied static assets under `app/public/paper/` for `policybench.org/paper`

Suggested workflow:

1. Install app dependencies if `app/node_modules` is absent:

   ```bash
   cd app && bun install --frozen-lockfile && cd ..
   ```

2. Install the render environment and render the manuscript:

   ```bash
   uv sync --extra docs
   uv run python paper/render_paper.py
   ```

Notes:
- This scaffold assumes `quarto` and the app dependencies are installed
  separately. The renderer reads PolicyEngine design-system tokens from
  `app/node_modules/@policyengine/design-system/dist/tokens.css`.
- The render is hermetic: it uses the standard `python3` Jupyter kernel pinned
  to the invoking virtualenv (`render_paper.py` sets `QUARTO_PYTHON` and
  `JUPYTER_PREFER_ENV_PATH=1`), so it always executes this checkout's
  `policybench`. No user-level kernelspec needs to be registered. The render
  environment lives in the `docs` extra (`uv sync --extra docs`).
- The manuscript tables and figures read from the frozen source run exports
  under `paper/snapshot/20260501/runs/`.
- `app/src/data.json` is the live site export. For this snapshot it must match
  the committed source-run dashboard exports under `paper/snapshot/20260501/runs/`.
- Frozen manuscript inputs that need to be versioned live under
  `paper/snapshot/`. Keep that directory committed with the manuscript.
- `paper/render_paper.py` generates temporary figures internally, copies the
  retained PDF/web outputs into `app/public/paper/`, and removes temporary
  `paper/out/` and `paper/figures/` outputs before exiting. Those scratch
  directories are ignored; `app/public/paper/` is the served artifact set.
- The app route at `/paper` is a landing page for the manuscript and links to the rendered assets once they exist.
