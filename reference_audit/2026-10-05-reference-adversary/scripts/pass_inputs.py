"""The reference adversary's inputs, staged from git and checked against pinned sha256s.

The pass read the frozen run as commit PASS_COMMIT (release dashboard-data-20260930,
#187) committed it, and built its reference system (policyengine-us 2.15.17 plus
``latest_final``) from the convention modules as that commit held them. Later commits
rewrite the working tree's copies: release dashboard-data-20261006 (#202) rewrote the
run's payload and exclusion record, and #204 rewrote
``latest_alt_snap_mortgage_residence.py``. So every script in this directory reads
these inputs only through ``git_input``: ``git show <commit>:<path>`` into scratch,
refused (SystemExit) unless the bytes match the pinned sha256, and read only from the
staged copy. A script stages everything it reads before it computes or writes
anything, and before it imports the engine. The code (this checkout's ``policybench``
package and the installed engine) is not pinned here; each script's own reproduction
check covers it.

``policybench`` loads its output definitions (``benchmark_specs.json``) itself, once
per process: first at import of ``policybench.scenarios``, and every spec lookup then
uses that copy. Those are an input, so ``use_staged_specs`` points the package at the
staged copy; the engine-side scripts call it in every process, workers included,
before they import anything else from ``policybench``. leaderboard_impact.py does not: it scores with ``policybench analyze``
in a child process and treats the definitions as part of the scoring code its
published-reproduction check covers.

The README's Inputs table lists every pin and the scripts that read it, and
tests/test_reference_adversary_inputs.py checks that the table and these pins agree.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Release dashboard-data-20260930 (#187): the frozen run, the output definitions and
# the reference system's convention modules, as the pass read them.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
RUN_SHA256 = {
    "data.json.gz": "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18",
    "predictions.csv.gz": (
        "ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12"
    ),
    "reference_outputs.csv": (
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466"
    ),
    "reference_outputs.csv.meta.json": (
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b"
    ),
    "reference_exclusions.json": (
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2"
    ),
    "scenarios.csv": "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a",
    "scenarios.csv.meta.json": (
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb"
    ),
}
SPECS_PATH = "policybench/benchmark_specs.json"
SPECS_SHA256 = "ce233f8cbb0549b33469b5929fc6df3cd5d064c727529afafe26ff2da7970cc5"
# latest_final and every module beside it, plus the sales tax table
# latest_c_irs_sales_tax_2025 reads; staged flat into one directory, as the
# reference builder copied them.
FIXES_SHA256 = {
    "reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json": (
        "7cf93799aad6a8c3a6fc70e7df4acc6043202a1ecc083f2c3101f76b87a85eae"
    ),
    "reference_audit/2026-09-28/fixes/alt_conventions_r25.py": (
        "0f77fdd44e758581f7e563b0f7b70c4d4359a833b08a4ac45a614c380938775e"
    ),
    "reference_audit/2026-09-28/fixes/latest_alt_r02_ira_219g.py": (
        "3e71bab1db867988544e6f87f6dda4dc7c719d51320fbbb7558cd574a0374f6e"
    ),
    "reference_audit/2026-09-28/fixes/latest_alt_salt_refund_no_prior_benefit.py": (
        "d8a314093466caf5fe0a226f1060acba2e4364c4b87befbd80639ebf41cc4a2c"
    ),
    "reference_audit/2026-09-28/fixes/latest_alt_snap_mortgage_residence.py": (
        "00cd13886a8c3d03c4e84944d35f7e8a1448af26838e8bc0761b914b887c70cd"
    ),
    "reference_audit/2026-09-28/fixes/latest_alt_unlisted_hours_40.py": (
        "5e6538a903112243ad85051ccba26b6133bdfbd5b9e5ba3dfa81ba690c061b32"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_ca_hold_2025.py": (
        "f19a47b9583032a0602a31e52f995eee824a427a76e87a9d4257d6682a016fa2"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_id_hold_2025.py": (
        "39fb99292691600cd273a1c6ef3c90847453e21e4d7b872603bcaac71727f8a5"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_irs_sales_tax_2025.py": (
        "7f7fd235b29c45d1d5cceded0c3391aceb38740518dfda770e3aebcc3003228e"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_md_2026.py": (
        "8111c77ffd2e43d434d083994a7e8506ba42461a0845b33ac47ce0df988c2c76"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_mi_published_2026.py": (
        "787cf837422e0bdf331a8e01a6fa8e8f2e3b78c35c248a4da83f3b2dbfa9ef9e"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_mn_published_2026.py": (
        "02a8ccc1fce71485fc9411d4a55f33226de4c8de09cf6375f99866b79da70522"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_mo_published_2026.py": (
        "0474524c83a7eb0c8440abf06bbeee38d4394e08260464d0dacb195ed3a8d916"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_snap_hold_fy2026.py": (
        "3a8709ef36582af2248e460136db618fd319d490b7aeed94adbd6143ad9c07dd"
    ),
    "reference_audit/2026-09-28/fixes/latest_c_wi_published_2026.py": (
        "4edf4c714c05d300e6fa32c4b56879aad8aa0de1d9ddd9a77987eefe3b06acce"
    ),
    "reference_audit/2026-09-28/fixes/latest_conventions.py": (
        "4155ed4a0be72c907815b33e2b3603cf0b5ea3eca351ad7509f8bd9ea5bb8ddb"
    ),
    "reference_audit/2026-09-28/fixes/latest_final.py": (
        "dbbdd228b99933c6f336af97970821c25c863a18606285e8d6d9ffb3bc9af78e"
    ),
    "reference_audit/2026-09-28/fixes/latest_map_stated_hours.py": (
        "b210e780a31cfa0a3a0da2c49a8068ee14f00029b3ed39c00be67a1e917eda21"
    ),
    "reference_audit/2026-09-28/fixes/latest_md_local_output_scope.py": (
        "53a6de3cd9b149467e5d86a5bb1fcc258e859478a7c16b7d3df951c713e423dd"
    ),
    "reference_audit/2026-09-28/fixes/latest_state_conventions.py": (
        "56e62e399d20ba8c8d9c5dc9bc7ea6681e74d2b529fa38561dbc8e8b2a90b442"
    ),
}

# PolicyEngine/policybench#194's cited classification of state paid-leave programs.
LAW_COMMIT = "049f4f091397e9c3ec2d9b21f3acbeb9c07c9764"
LAW_PATH = "reference_audit/2026-10-05-payroll/program_classification.json"
LAW_SHA256 = "282cbf25ce9110a3c5c51873b7ca0e89f1f5ed38592b0c5b51d393f08000089a"

# The pass's own records as #200 merged them.
RECORDS_COMMIT = "4db91b5f10581947f60a07f899e0ec2867b0405e"
PROPOSALS_PATH = "reference_audit/2026-10-05-reference-adversary/proposed_changes.json"
PROPOSALS_SHA256 = "3a6e5920a2d02e94e1df52c95c1def2739f3eb21b1fb67fc74a7d68219a749bf"
CONFORMANCE_PATH = (
    "reference_audit/2026-10-05-reference-adversary/verification/"
    "definition_conformance.json"
)
CONFORMANCE_SHA256 = "05e503f1b291c505b90182395c4afb88844dcb45fb2952c004ca09d4273894a0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_bytes(commit: str, path: str, pinned: str) -> bytes:
    """``path`` as ``commit`` holds it, refusing any bytes but the pinned ones."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {path} at {commit[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"{commit[:12]}:{path} has sha256 {digest}, not the pinned {pinned}"
        )
    return result.stdout


def git_input(commit: str, path: str, pinned: str, target: Path) -> Path:
    """Write ``path`` as ``commit`` holds it to ``target``, refusing any other bytes."""
    data = git_bytes(commit, path, pinned)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def stage_run(target: Path, names: Iterable[str] | None = None) -> Path:
    """The frozen run's files ``names`` (default: all) as PASS_COMMIT holds them, in an
    empty ``target``."""
    if target.exists():
        shutil.rmtree(target)
    for name in RUN_SHA256 if names is None else names:
        git_input(PASS_COMMIT, f"{RUN_PATH}/{name}", RUN_SHA256[name], target / name)
    return target


def stage_fixes(target: Path) -> Path:
    """``latest_final``, its parts and the sales tax table, flat in an empty ``target``."""
    if target.exists():
        shutil.rmtree(target)
    for path, pinned in FIXES_SHA256.items():
        git_input(PASS_COMMIT, path, pinned, target / Path(path).name)
    return target


def stage_specs(target: Path) -> Path:
    """The output definitions as PASS_COMMIT holds them, written to ``target``."""
    return git_input(PASS_COMMIT, SPECS_PATH, SPECS_SHA256, target)


def use_staged_specs(path: Path) -> None:
    """Make ``policybench`` read its output definitions from the staged ``path``.

    For this process only; call it before importing anything else from
    ``policybench``, because ``policybench.scenarios`` derives module constants from
    the definitions as it is imported. If the package has already loaded its
    definitions (a long-lived interpreter, such as a test run), they must equal the
    staged ones, or the script stops: constants derived from other definitions
    cannot be recalled.
    """
    from policybench import spec

    staged = json.loads(path.read_text(encoding="utf-8"))
    if spec._raw_spec_data.cache_info().currsize and spec._raw_spec_data() != staged:
        raise SystemExit(
            "policybench already loaded output definitions that are not the pinned "
            f"{SPECS_PATH}; run this script in a fresh interpreter"
        )
    spec._spec_path = lambda: path
    spec._raw_spec_data.cache_clear()
    spec.get_benchmark_spec.cache_clear()
