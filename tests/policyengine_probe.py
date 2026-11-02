"""A process probe for end-to-end tests of the PolicyEngine provenance handoff.

``probe_environment`` returns an environment whose Python processes load a
sitecustomize. In every process it records which PolicyEngine modules are
loaded at exit; in eval-no-tools workers it also swaps the LLM transport in
policybench.eval_no_tools for a local fake that returns a schema-valid
forced-tool answer and records the modules loaded at each request. No
network, no spend.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

from policybench.policyengine_runtime import POLICYENGINE_PROVENANCE_ENV

REPO_ROOT = Path(__file__).resolve().parents[1]

PROCESS_PROBE = textwrap.dedent(
    """
    import atexit
    import importlib.abc
    import importlib.machinery
    import json
    import os
    import sys

    HEAVY = {
        "policyengine",
        "policyengine_core",
        "policyengine_uk",
        "policyengine_us",
        "h5py",
    }
    requests = []


    def heavy_modules():
        return sorted(
            name for name in list(sys.modules) if name.split(".")[0] in HEAVY
        )


    def fake_completion(**kwargs):
        from types import SimpleNamespace

        import litellm

        requests.append(heavy_modules())
        function = kwargs["tools"][0]["function"]
        properties = function["parameters"]["properties"]
        if "outputs" in properties:
            arguments = {
                "outputs": {
                    variable: {"value": 1, "explanation": "so it is 1"}
                    for variable in properties["outputs"]["properties"]
                }
            }
        else:
            arguments = {variable: "so it is 1" for variable in properties}
        call = SimpleNamespace(
            function=SimpleNamespace(
                name=function["name"], arguments=json.dumps(arguments)
            )
        )
        message = SimpleNamespace(content=None, function_call=None, tool_calls=[call])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
            usage=litellm.Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


    class PatchingLoader(importlib.abc.Loader):
        def __init__(self, inner):
            self.inner = inner

        def create_module(self, spec):
            return self.inner.create_module(spec)

        def exec_module(self, module):
            self.inner.exec_module(module)
            module.completion = fake_completion
            module.responses = fake_completion


    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname != "policybench.eval_no_tools":
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
            spec.loader = PatchingLoader(spec.loader)
            return spec


    sys.meta_path.insert(0, Finder())


    @atexit.register
    def dump():
        record = {"argv": sys.argv, "requests": requests, "at_exit": heavy_modules()}
        directory = os.environ["POLICYBENCH_TEST_PROBE_DIR"]
        with open(os.path.join(directory, f"{os.getpid()}.json"), "w") as handle:
            json.dump(record, handle)
    """
)


def clean_environment() -> dict[str, str]:
    """This process's environment, importing this checkout, with no
    provenance file handed down from outside the test."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key != POLICYENGINE_PROVENANCE_ENV
    }
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    return env


def probe_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """An environment that probes every Python process it starts, and the
    directory the probes write their records to."""
    hook_dir = tmp_path / "probe_hook"
    hook_dir.mkdir(exist_ok=True)
    (hook_dir / "sitecustomize.py").write_text(PROCESS_PROBE)
    probe_dir = tmp_path / "probe_records"
    probe_dir.mkdir(exist_ok=True)
    env = clean_environment()
    env.update(
        {
            "PYTHONPATH": os.pathsep.join([str(hook_dir), env["PYTHONPATH"]]),
            "POLICYBENCH_TEST_PROBE_DIR": str(probe_dir),
            "POLICYBENCH_CACHE_DIR": str(tmp_path / "cache"),
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        }
    )
    return env, probe_dir


def probe_records(probe_dir: Path) -> list[dict]:
    """One record per probed process: its argv, the PolicyEngine modules
    loaded at each LLM request, and those loaded at exit."""
    return [json.loads(path.read_text()) for path in sorted(probe_dir.glob("*.json"))]
