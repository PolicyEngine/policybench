"""2026 alternative: the prompt's unspecified $56 interest is ordinary Part A.

Includes the confirmed dividend-loss fix. Under M.G.L. c. 62 section 2(b)(1),
ordinary taxable interest belongs in Part A unless a statutory exception applies.
This is an alternative source reading, not proof that the bank was outside MA.
The benchmark's sole MA case has no U.S.-obligation interest or other exception.
"""

import importlib.util
from pathlib import Path

_path = Path(__file__).with_name("ma_part_a_loss_offset.py")
_spec = importlib.util.spec_from_file_location("ma_loss_offset", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

FIX_ID = "ma_part_a_ordinary_interest"
DESCRIPTION = "2026 MA loss-offset fix plus the ordinary Part A reading of unspecified interest."
reform = _module.build(ordinary_interest=True)
