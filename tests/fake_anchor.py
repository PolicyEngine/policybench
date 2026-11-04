"""The confirmatory runner's anchor command in its tests: a copy of the run's
anchors.jsonl to FOLDER/anchored.jsonl.

Usage: python fake_anchor.py FOLDER ANCHORS
"""

import shutil
import sys
from pathlib import Path

folder, anchors = Path(sys.argv[1]), Path(sys.argv[2])
shutil.copyfile(anchors, folder / "anchored.jsonl")
print("anchored")
