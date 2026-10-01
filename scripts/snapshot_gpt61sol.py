"""Copy GPT-6.1 Sol's completed scenario CSVs for a PARTIAL rehearsal.

Runs snapshot_adds0928.py's copier over finish_gpt61sol.MODELS without reading
live run state. It writes a synthetic incomplete run_state.json (total=100):
finish_gpt61sol.py --early refuses it; set total=completed in the scratch copy
only, then use --early --partial. The synthetic state carries no evidence
about the supervisor's actual serving fingerprint.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import finish_gpt61sol as driver  # noqa: E402
import snapshot_adds0928 as copier  # noqa: E402


def main() -> None:
    names = ("MODELS", "ROOT", "SNAPSHOT", "validate_stage_path")
    saved = {name: getattr(copier, name) for name in names}
    try:
        for name in names:
            setattr(copier, name, getattr(driver, name))
        copier.main()
    finally:
        for name, value in saved.items():
            setattr(copier, name, value)


if __name__ == "__main__":
    main()
