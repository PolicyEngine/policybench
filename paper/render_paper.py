"""Render the PolicyBench paper and publish static assets into the app."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "paper"
PUBLIC_PAPER_DIR = ROOT / "app" / "public" / "paper"
PUBLIC_WEB_DIR = PUBLIC_PAPER_DIR / "web"
EXPORT_DIR = ROOT / "results" / "paper_exports"
DESIGN_SYSTEM_TOKENS = (
    ROOT
    / "app"
    / "node_modules"
    / "@policyengine"
    / "design-system"
    / "dist"
    / "tokens.css"
)


def find_executable(name: str, fallbacks: list[Path]) -> str | None:
    path = shutil.which(name)
    if path is not None:
        return path
    for candidate in fallbacks:
        if candidate.exists():
            return str(candidate)
    return None


def copy_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def ensure_web_index(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    index_path = destination / "index.html"
    if index_path.exists():
        return

    index_path.write_text(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PolicyBench paper</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #0a1013;
        --panel: #10181d;
        --border: rgba(255,255,255,0.1);
        --text: #f3f7fa;
        --muted: #a9b8c2;
        --accent: #7dd3a7;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Inter, ui-sans-serif, system-ui, sans-serif;
        background: var(--bg);
        color: var(--text);
      }
      header {
        position: sticky;
        top: 0;
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.9rem 1.25rem;
        border-bottom: 1px solid var(--border);
        background: rgba(10,16,19,0.92);
        backdrop-filter: blur(14px);
      }
      header a {
        color: inherit;
        text-decoration: none;
      }
      .brand {
        font-size: 1.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
      }
      .meta {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--muted);
      }
      main {
        padding: 1rem;
      }
      .card {
        max-width: 1100px;
        margin: 0 auto;
        border: 1px solid var(--border);
        border-radius: 20px;
        background: var(--panel);
        overflow: hidden;
      }
      .actions {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid var(--border);
      }
      .actions p {
        margin: 0;
        color: var(--muted);
        font-size: 0.95rem;
      }
      .actions .links {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
      }
      .actions .links a {
        color: var(--accent);
      }
      iframe {
        display: block;
        width: 100%;
        height: calc(100vh - 170px);
        border: 0;
        background: white;
      }
      @media (max-width: 640px) {
        .actions {
          flex-direction: column;
        }
        iframe {
          height: calc(100vh - 220px);
        }
      }
    </style>
  </head>
  <body>
    <header>
      <a class="brand" href="/">PolicyBench</a>
      <div class="meta">Paper</div>
    </header>
    <main>
      <section class="card">
        <div class="actions">
          <p>Browser paper view. Download the PDF if the embed is slow on your device.</p>
          <div class="links">
            <a href="/paper/policybench.pdf">Download PDF</a>
            <a href="/paper">Paper landing</a>
          </div>
        </div>
        <iframe src="/paper/policybench.pdf" title="PolicyBench paper PDF"></iframe>
      </section>
    </main>
  </body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    quarto = find_executable(
        "quarto",
        [
            Path.home() / "quarto" / "bin" / "quarto",
            Path("/opt/homebrew/bin/quarto"),
            Path("/usr/local/bin/quarto"),
        ],
    )
    if quarto is None:
        raise SystemExit(
            "Quarto is not installed. Install it first, then rerun "
            "`./.venv/bin/python paper/render_paper.py`."
        )

    env = dict(os.environ)
    tex_bin = Path("/Library/TeX/texbin")
    if tex_bin.exists():
        env["PATH"] = f"{tex_bin}:{env.get('PATH', '')}"
    env["QUARTO_PYTHON"] = sys.executable

    if not (EXPORT_DIR / "benchmark_snapshot.json").exists():
        raise SystemExit(
            "Missing frozen paper exports in results/paper_exports. "
            "Regenerate them before rendering."
        )
    if (ROOT / "results" / "full_batch_20260329_1000" / "analysis").exists() and (
        ROOT / "results" / "uk_full_batch_20260329_1000" / "analysis"
    ).exists():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "export_paper_artifacts.py")],
            check=True,
            cwd=ROOT,
            env=env,
        )
    subprocess.run(
        [sys.executable, str(PAPER_DIR / "generate_figures.py")],
        check=True,
        cwd=ROOT,
        env=env,
    )
    if not DESIGN_SYSTEM_TOKENS.exists():
        raise SystemExit(
            "Missing PolicyEngine design tokens at "
            f"{DESIGN_SYSTEM_TOKENS}. Run `bun install` in app first."
        )
    copy_if_exists(DESIGN_SYSTEM_TOKENS, PAPER_DIR / "pe-tokens.css")

    html_out_dir = PAPER_DIR / "out" / "web"
    pdf_out_dir = PAPER_DIR / "out" / "pdf"
    if html_out_dir.exists():
        shutil.rmtree(html_out_dir)
    if pdf_out_dir.exists():
        shutil.rmtree(pdf_out_dir)

    subprocess.run(
        [
            quarto,
            "render",
            "index.qmd",
            "--to",
            "html",
            "--output-dir",
            str(html_out_dir),
        ],
        check=True,
        cwd=PAPER_DIR,
        env=env,
    )
    subprocess.run(
        [
            quarto,
            "render",
            "index.qmd",
            "--to",
            "pdf",
            "--output-dir",
            str(pdf_out_dir),
        ],
        check=True,
        cwd=PAPER_DIR,
        env=env,
    )

    copy_tree(html_out_dir, PUBLIC_WEB_DIR)
    ensure_web_index(PUBLIC_WEB_DIR)

    pdf_candidates = [
        pdf_out_dir / "policybench.pdf",
        pdf_out_dir / "index.pdf",
    ]
    for candidate in pdf_candidates:
        if candidate.exists():
            copy_if_exists(candidate, PUBLIC_PAPER_DIR / "policybench.pdf")
            break

    print("Rendered paper assets into app/public/paper")


if __name__ == "__main__":
    main()
