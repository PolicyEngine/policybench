"""The confirmatory runner's anchor command in its tests: a copy of the run's
anchors.jsonl to FOLDER/anchored.jsonl.

Usage: python fake_anchor.py [--repo CLONE] FOLDER ANCHORS
"""

import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path)
parser.add_argument("folder", type=Path)
parser.add_argument("anchors", type=Path)
args = parser.parse_args()
shutil.copyfile(args.anchors, args.folder / "anchored.jsonl")
print("anchored")
