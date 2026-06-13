"""Model-assisted failure audit of wrong predictions.

Each wrong ``(scenario_id, variable)`` case groups every model that missed the
PolicyEngine reference for that household-output target. A classifier reviews
the case — the question the models were asked, how PolicyEngine derived the
reference, and each wrong model's answer and explanation — and assigns a
structured failure category from :mod:`policybench.annotation_taxonomy`, plus a
free-text rationale and an explicit flag for whether the *reference* itself
looks suspect (a candidate PolicyEngine or data bug worth filing upstream
before a snapshot is frozen).

The classifier backend is pluggable. The default is the Codex CLI, run
non-interactively so the work bills to a ChatGPT plan rather than a metered
API key; ``scripts/run_audit_codex.sh`` is the bulk runner. This module owns
the deterministic halves — assembling case context (``prepare_audit``) and
folding verdicts back into the annotation schema (``collect_audit``) — so the
LLM step is the only non-deterministic link and is fully resumable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from policybench.annotation_taxonomy import (
    FAILURE_SOURCE_VALUES,
    FAILURE_SUBTYPE_VALUES,
    validate_failure_source,
    validate_failure_subtype,
)
from policybench.case_annotations import _format_value, wrong_prediction_rows
from policybench.full_run_export import load_case_reference_explanations
from policybench.spec import metric_type_for_output

# Reference-suspect verdicts route a case to an upstream PolicyEngine/data fix
# rather than scoring the models against a value the audit doubts.
REFERENCE_SUSPECT_SOURCES = frozenset(
    {"reference_model_issue_fixed", "reference_data_issue_fixed"}
)


@dataclass(frozen=True)
class WrongModel:
    """One model's miss on a case."""

    model: str
    prediction: str
    explanation: str


@dataclass(frozen=True)
class AuditCase:
    """A single ``(scenario_id, variable)`` case for classification."""

    case_id: str
    country: str
    scenario_id: str
    variable: str
    metric_type: str
    reference_value: str
    reference_derivation: str
    question: str
    wrong_models: tuple[WrongModel, ...]

    def to_manifest_row(self) -> dict:
        row = asdict(self)
        row["wrong_models"] = [m.model for m in self.wrong_models]
        return row


def _case_id(country: str, scenario_id: str, variable: str) -> str:
    """Filesystem-safe identifier for a case directory."""
    safe = f"{country}__{scenario_id}__{variable}"
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in safe)


def build_audit_cases(country_dir: Path) -> list[AuditCase]:
    """Assemble one :class:`AuditCase` per wrong ``(scenario_id, variable)``."""
    country = country_dir.name
    wrong = wrong_prediction_rows(country_dir)
    if wrong.empty:
        return []

    derivations = load_case_reference_explanations(country_dir)
    derivation_by_case: dict[tuple[str, str], str] = {}
    if not derivations.empty and "explanation" in derivations.columns:
        for _, row in derivations.iterrows():
            derivation_by_case[(str(row["scenario_id"]), str(row["variable"]))] = str(
                row.get("explanation") or ""
            )

    questions = _scenario_questions(country_dir)

    cases: list[AuditCase] = []
    group_cols = ["scenario_id", "variable"]
    for (scenario_id, variable), group in wrong.groupby(group_cols, sort=True):
        metric_type = metric_type_for_output(variable)
        reference_value = _format_value(
            group["value"].iloc[0], country=country, variable=variable
        )
        wrong_models = tuple(
            WrongModel(
                model=str(r["model"]),
                prediction=_format_value(
                    r["prediction"], country=country, variable=variable
                ),
                explanation=_clean(r.get("explanation")),
            )
            for _, r in group.sort_values("model").iterrows()
        )
        cases.append(
            AuditCase(
                case_id=_case_id(country, str(scenario_id), str(variable)),
                country=country,
                scenario_id=str(scenario_id),
                variable=str(variable),
                metric_type=metric_type,
                reference_value=reference_value,
                reference_derivation=derivation_by_case.get(
                    (str(scenario_id), str(variable)), ""
                ),
                question=questions.get((str(scenario_id), str(variable)), ""),
                wrong_models=wrong_models,
            )
        )
    return cases


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _scenario_questions(country_dir: Path) -> dict[tuple[str, str], str]:
    """Map ``(scenario_id, variable)`` to the exact prompt the models received.

    Best-effort: returns an empty map when the scenario manifest lacks the
    ``scenario_json`` needed to rebuild prompts. The audit still works without
    it — model explanations restate the relevant household facts — so a missing
    manifest degrades context rather than failing the run.
    """
    manifest = country_dir / "scenarios.csv"
    if not manifest.exists():
        return {}
    scenarios = pd.read_csv(manifest)
    if "scenario_json" not in scenarios.columns:
        return {}
    from policybench.analysis import build_scenario_prompt_map

    variables = sorted(str(v) for v in scenarios.get("variable", pd.Series()).unique())
    if not variables:
        # The manifest is one row per scenario; variables come from the wrong set.
        wrong = wrong_prediction_rows(country_dir)
        variables = sorted(str(v) for v in wrong["variable"].unique())
    prompt_map = build_scenario_prompt_map(scenarios, variables)
    out: dict[tuple[str, str], str] = {}
    for scenario_id, by_variable in prompt_map.items():
        for variable, by_contract in by_variable.items():
            prompt = by_contract.get("tool") or next(iter(by_contract.values()), "")
            if prompt:
                out[(str(scenario_id), str(variable))] = prompt
    return out


# --- Classification contract -------------------------------------------------

AUDIT_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reference_suspect": {
            "type": "boolean",
            "description": (
                "True only if the PolicyEngine reference value itself looks "
                "wrong — a candidate model or data bug — rather than the AI "
                "models being wrong."
            ),
        },
        "reference_bug_hypothesis": {
            "type": "string",
            "description": (
                "If reference_suspect, a one-sentence hypothesis for the "
                "PolicyEngine/data bug; otherwise an empty string."
            ),
        },
        "case_failure_source": {"type": "string", "enum": list(FAILURE_SOURCE_VALUES)},
        "case_failure_subtype": {
            "type": "string",
            "enum": list(FAILURE_SUBTYPE_VALUES),
        },
        "rationale": {
            "type": "string",
            "description": "2-4 sentence explanation of the classification.",
        },
        "models": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "model": {"type": "string"},
                    "failure_source": {
                        "type": "string",
                        "enum": list(FAILURE_SOURCE_VALUES),
                    },
                    "failure_subtype": {
                        "type": "string",
                        "enum": list(FAILURE_SUBTYPE_VALUES),
                    },
                },
                "required": ["model", "failure_source", "failure_subtype"],
            },
        },
    },
    "required": [
        "reference_suspect",
        "reference_bug_hypothesis",
        "case_failure_source",
        "case_failure_subtype",
        "rationale",
        "models",
    ],
}

_PROMPT_HEADER = """\
You are auditing why AI models missed a PolicyEngine reference value on a \
US/UK tax-and-benefit estimation benchmark. The models answered from \
parametric knowledge with no tools; PolicyEngine's microsimulation is the \
reference. Classify the failure for this one case.

Decide, conservatively:
1. Is the PolicyEngine REFERENCE itself likely wrong (a model/data bug worth \
filing upstream)? Set reference_suspect=true ONLY with concrete evidence \
(e.g. the reference contradicts the stated rules, or every model agrees on a \
value that is clearly correct against the law). Default to false — the models \
are usually the ones in error.
2. Otherwise, classify each model's miss into a failure_subtype, and give the \
case a primary failure_source/subtype.

failure_source meanings:
- llm_error: the model reasoned or computed incorrectly (the usual case).
- prompt_ambiguity: the question is genuinely ambiguous; a careful expert \
could read it more than one way.
- reference_model_issue_fixed / reference_data_issue_fixed: the reference \
value looks wrong (PolicyEngine logic / underlying data). Use with \
reference_suspect=true.
- parse_contract_failure: the model's answer was missing or unparseable, not a \
substantive error.
- needs_review: genuinely cannot tell.

Output ONLY the JSON verdict matching the schema. Do not run any commands; all \
information you need is below.
"""


def render_case_prompt(case: AuditCase) -> str:
    """Render the self-contained classification prompt for one case."""
    lines = [
        _PROMPT_HEADER,
        f"\nCOUNTRY: {case.country.upper()}",
        f"OUTPUT (variable): {case.variable}  [{case.metric_type}]",
        f"POLICYENGINE REFERENCE VALUE: {case.reference_value}",
    ]
    if case.reference_derivation:
        lines.append(
            f"\nHOW POLICYENGINE DERIVED THE REFERENCE:\n{case.reference_derivation}"
        )
    if case.question:
        lines.append(f"\nQUESTION SHOWN TO THE MODELS:\n{case.question}")
    lines.append(f"\nWRONG MODEL ANSWERS ({len(case.wrong_models)}):")
    for m in case.wrong_models:
        expl = m.explanation or "(no explanation provided)"
        lines.append(f"\n- {m.model}: answered {m.prediction}\n  reasoning: {expl}")
    lines.append(
        "\nReturn the JSON verdict. Include one entry in `models` for every "
        "model listed above, using these exact model ids: "
        + ", ".join(m.model for m in case.wrong_models)
    )
    return "\n".join(lines)


def prepare_audit(country_dir: Path, audit_dir: Path) -> list[AuditCase]:
    """Write per-case prompts, the shared output schema, and a manifest.

    Layout under ``audit_dir``::

        schema.json
        cases.jsonl
        cases/<case_id>/prompt.md
        cases/<case_id>/verdict.json   (written later by the runner)
    """
    cases = build_audit_cases(country_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA, indent=2))
    cases_root = audit_dir / "cases"
    cases_root.mkdir(exist_ok=True)
    with (audit_dir / "cases.jsonl").open("w") as manifest:
        for case in cases:
            case_dir = cases_root / case.case_id
            case_dir.mkdir(exist_ok=True)
            (case_dir / "prompt.md").write_text(render_case_prompt(case))
            manifest.write(json.dumps(case.to_manifest_row()) + "\n")
    return cases


# --- Verdict collection ------------------------------------------------------


def _load_manifest(audit_dir: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    manifest = audit_dir / "cases.jsonl"
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["case_id"]] = row
    return rows


def parse_verdict(path: Path) -> dict | None:
    """Parse a Codex verdict file, tolerating prose wrapped around the JSON."""
    if not path.exists():
        return None
    text = path.read_text().strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def collect_audit(country_dir: Path, audit_dir: Path) -> dict[str, pd.DataFrame]:
    """Fold verdicts into the annotation schema.

    Returns ``{"row": ..., "case": ..., "missing": ...}``. ``row`` and ``case``
    match the committed annotation CSV columns, extended with ``rationale`` and
    ``reference_suspect`` so the classifier's reasoning is preserved. ``missing``
    lists cases whose verdict has not yet been produced (resumability).
    """
    manifest = _load_manifest(audit_dir)
    cases_root = audit_dir / "cases"
    country = country_dir.name

    row_records: list[dict] = []
    case_records: list[dict] = []
    missing: list[str] = []

    for case_id, meta in manifest.items():
        verdict = parse_verdict(cases_root / case_id / "verdict.json")
        if verdict is None:
            missing.append(case_id)
            continue
        case_source = validate_failure_source(verdict["case_failure_source"])
        case_subtype = validate_failure_subtype(verdict["case_failure_subtype"])
        reference_suspect = bool(verdict.get("reference_suspect"))
        rationale = str(verdict.get("rationale", "")).strip()
        per_model = {
            str(m["model"]): m for m in verdict.get("models", []) if m.get("model")
        }
        for model in meta["wrong_models"]:
            entry = per_model.get(model, {})
            row_records.append(
                {
                    "country": country,
                    "scenario_id": meta["scenario_id"],
                    "variable": meta["variable"],
                    "model": model,
                    "failure_source": validate_failure_source(
                        entry.get("failure_source", case_source)
                    ),
                    "failure_subtype": validate_failure_subtype(
                        entry.get("failure_subtype", case_subtype)
                    ),
                    "reference_suspect": reference_suspect,
                    "annotation": rationale,
                }
            )
        case_records.append(
            {
                "country": country,
                "scenario_id": meta["scenario_id"],
                "variable": meta["variable"],
                "wrong_model_count": len(meta["wrong_models"]),
                "case_failure_source": case_source,
                "case_failure_subtype": case_subtype,
                "reference_suspect": reference_suspect,
                "reference_bug_hypothesis": str(
                    verdict.get("reference_bug_hypothesis", "")
                ).strip(),
                "case_annotation": rationale,
            }
        )
    return {
        "row": pd.DataFrame(row_records),
        "case": pd.DataFrame(case_records),
        "missing": pd.DataFrame({"case_id": missing}),
    }
