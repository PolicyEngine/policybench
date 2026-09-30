"""The reference system for the 2026-09-28 wave: policyengine-us 2.15.17 plus
latest_conventions (the nine pre-freeze-law conventions) plus
latest_md_local_output_scope (the output-definition adapter that keeps Maryland county
income tax out of the state income tax output). The stated-hours mapping lives in
policybench.scenarios (PE_INPUT_ALIASES), not here."""

import importlib.util
import sys
from pathlib import Path

from policyengine_core.reforms import Reform

FIX_ID = "latest_final"
DESCRIPTION = "latest_conventions + latest_md_local_output_scope on policyengine-us 2.15.17"
PARTS = ("latest_conventions", "latest_md_local_output_scope")


def _load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(f"latest_final_part_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REFORMS = tuple(_load(name).reform for name in PARTS)


class reform(Reform):
    def apply(self):
        for part in REFORMS:
            part.apply(self)
