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

import hashlib
import json
import re
import shutil
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
from policybench.judge_template import (
    JUDGE_TEMPLATE_HEADERS,
    TEMPLATE_VERSION_FIELD,
    recorded_template_version,
    template_header,
    template_version_of,
)
from policybench.spec import metric_type_for_output

# _format_value renders a missing/NaN prediction as this sentinel; such a miss
# is a parse failure, not a substantive error.
MISSING_VALUE = "missing"


@dataclass(frozen=True)
class WrongModel:
    """One model's miss on a case."""

    model: str
    prediction: str
    explanation: str
    failure_source: str = ""


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
    grounding: str = ""

    def to_manifest_row(self) -> dict:
        row = asdict(self)
        row["recorded_failure_sources"] = {
            model.model: model.failure_source
            for model in self.wrong_models
            if model.failure_source == "budget_exhausted_at_ceiling"
        }
        row["wrong_models"] = [m.model for m in self.wrong_models]
        missing = [m.model for m in self.wrong_models if m.prediction == MISSING_VALUE]
        row["missing_models"] = missing
        # A case whose every wrong model simply returned no value needs no LLM:
        # each miss is deterministically a parse_contract_failure / missing_output.
        row["parse_failure_only"] = len(missing) == len(self.wrong_models)
        return row


def _case_id(country: str, scenario_id: str, variable: str) -> str:
    """Filesystem-safe identifier for a case directory."""
    safe = f"{country}__{scenario_id}__{variable}"
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in safe)


def build_audit_cases(
    country_dir: Path,
    grounding_lookup: dict[tuple[str, str], str] | None = None,
) -> list[AuditCase]:
    """Assemble one :class:`AuditCase` per wrong ``(scenario_id, variable)``.

    ``grounding_lookup`` optionally maps ``(scenario_id, variable)`` to a block
    of authoritative engine facts (e.g. the Medicaid eligibility category from
    the reference trace) rendered into the case prompt.
    """
    country = country_dir.name
    wrong = wrong_prediction_rows(country_dir)
    if wrong.empty:
        return []

    derivations = load_case_reference_explanations(country_dir)
    derivation_by_case: dict[tuple[str, str], str] = {}
    if not derivations.empty and "reference_explanation" in derivations.columns:
        for _, row in derivations.iterrows():
            derivation_by_case[(str(row["scenario_id"]), str(row["variable"]))] = str(
                row.get("reference_explanation") or ""
            )

    variables = sorted(str(v) for v in wrong["variable"].unique())
    questions = _scenario_questions(country_dir, variables)

    cases: list[AuditCase] = []
    group_cols = ["scenario_id", "variable"]
    for (scenario_id, variable), group in wrong.groupby(group_cols, sort=True):
        metric_type = metric_type_for_output(variable)
        reference_value = _format_value(
            group["value"].iloc[0], country=country, variable=variable
        )
        # A model can appear more than once per cell across repeated runs; keep
        # one row per model so wrong_models (and wrong_model_count) stay unique
        # and the collected annotations don't trip the duplicate-key guard.
        deduped = group.sort_values("model").drop_duplicates("model", keep="first")
        wrong_models = tuple(
            WrongModel(
                model=str(r["model"]),
                prediction=_format_value(
                    r["prediction"], country=country, variable=variable
                ),
                explanation=_clean(r.get("explanation")),
                failure_source=_clean(r.get("failure_source")),
            )
            for _, r in deduped.iterrows()
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
                grounding=(grounding_lookup or {}).get(
                    (str(scenario_id), str(variable)), ""
                ),
            )
        )
    return cases


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _scenario_questions(
    country_dir: Path, variables: list[str]
) -> dict[tuple[str, str], str]:
    """Map ``(scenario_id, variable)`` to the exact prompt the models received.

    Best-effort: returns an empty map when the scenario manifest lacks the
    ``scenario_json`` needed to rebuild prompts. The audit still works without
    it — model explanations restate the relevant household facts — so a missing
    manifest degrades context rather than failing the run.
    """
    manifest = country_dir / "scenarios.csv"
    if not manifest.exists() or not variables:
        return {}
    scenarios = pd.read_csv(manifest)
    if "scenario_json" not in scenarios.columns:
        return {}
    from policybench.analysis import build_scenario_prompt_map

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
            "description": (
                "2-4 sentences on the shared trap: the specific rule or "
                "computation step that separates the reference from the wrong "
                "answers in this case. Definitive voice; never discuss "
                "whether the reference is correct here."
            ),
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
                    "diagnosis": {
                        "type": "string",
                        "description": (
                            "1-3 definitive sentences: the exact rule, "
                            "eligibility pathway, deduction, threshold, or "
                            "computation step THIS model missed or "
                            "misapplied, grounded in its own stated "
                            "reasoning (or, absent reasoning, in what its "
                            "answer implies it computed). No hedging; never "
                            "discuss whether the reference is correct."
                        ),
                    },
                },
                "required": [
                    "model",
                    "failure_source",
                    "failure_subtype",
                    "diagnosis",
                ],
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

# The judge's prompt is a versioned header (policybench.judge_template) and
# the case. A verdict is carried only on the exact bytes it was judged on, so
# a seed case renders with the version its sidecar records. Every caller names
# the version: nothing here picks one by default or reads one off a prompt.


def render_case_prompt(case: AuditCase, *, template_version: int) -> str:
    """Render the self-contained classification prompt for one case.

    ``template_version`` picks the header (``JUDGE_TEMPLATE_HEADERS``); the
    rest of the prompt does not depend on it. It has no default: a release
    reproduces its prompts only on the version its verdicts were judged on.
    """
    lines = [
        template_header(template_version),
        f"\nCOUNTRY: {case.country.upper()}",
        f"OUTPUT (variable): {case.variable}  [{case.metric_type}]",
        f"POLICYENGINE REFERENCE VALUE: {case.reference_value}",
    ]
    if case.reference_derivation:
        lines.append(
            "\nHOW POLICYENGINE DERIVED THE REFERENCE (generated from the "
            f"engine's computation trace):\n{case.reference_derivation}"
        )
    if case.grounding:
        lines.append(
            "\nAUTHORITATIVE ENGINE FACTS (from the reference trace; every "
            f"diagnosis must agree with these):\n{case.grounding}"
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


def prepare_audit(
    country_dir: Path,
    audit_dir: Path,
    grounding_lookup: dict[tuple[str, str], str] | None = None,
    *,
    template_version: int,
) -> list[AuditCase]:
    """Write per-case prompts, the shared output schema, and a manifest.

    Layout under ``audit_dir``::

        schema.json
        cases.jsonl
        cases/<case_id>/prompt.md
        cases/<case_id>/verdict.json        (written later by the runner)
        cases/<case_id>/verdict.meta.json   (its provenance sidecar)

    A case that already has a verdict (a seed a release driver copied in, or
    an earlier run's) keeps it only on the exact bytes its judge read
    (:func:`_judged_prompt`): the case rendered on the template version its
    sidecar records (absent: v1) must equal its prompt.md byte for byte, or,
    when prompt.md is missing, hash to the ``prompt_sha256`` its sidecar
    records. A kept case's files are left untouched. Otherwise the case
    changed since it was judged, or its version or judged bytes are unknown:
    the verdict and its sidecar are dropped and the case is re-opened. New
    and re-opened cases are rendered with ``template_version``, which the
    caller must name. The version a case renders with comes from the sidecar
    or the caller, never from prompt.md: a prompt that begins with another
    version's header is not adopted. Prompts are written as UTF-8 bytes, with
    no newline translation.
    """
    template_header(template_version)
    cases = build_audit_cases(country_dir, grounding_lookup=grounding_lookup)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA, indent=2))
    cases_root = audit_dir / "cases"
    cases_root.mkdir(exist_ok=True)
    rows = [case.to_manifest_row() for case in cases]
    # Only substantive cases (at least one model gave a real, wrong value) get a
    # prompt + case dir; pure parse-failure cases are recorded in the manifest
    # and classified deterministically at collect time — no classifier call.
    substantive_ids = {
        case.case_id for case, row in zip(cases, rows) if not row["parse_failure_only"]
    }
    # Prune orphan dirs (cases that vanished or flipped to parse-failure-only),
    # so the runner never bills the classifier for them. Still-current
    # substantive cases keep their dir (and any verdict) for resumability.
    for child in cases_root.iterdir():
        if child.is_dir() and child.name not in substantive_ids:
            shutil.rmtree(child)
    with (audit_dir / "cases.jsonl").open("w") as manifest:
        for case, row in zip(cases, rows):
            manifest.write(json.dumps(row) + "\n")
            if row["parse_failure_only"]:
                continue
            case_dir = cases_root / case.case_id
            case_dir.mkdir(exist_ok=True)
            prompt_path = case_dir / "prompt.md"
            verdict_path = case_dir / "verdict.json"
            if verdict_path.exists():
                judged = _judged_prompt(case, case_dir)
                if judged is not None:
                    # The verdict stands on these bytes. A prompt.md the
                    # sidecar's hash vouched for is restored.
                    if not prompt_path.exists():
                        prompt_path.write_bytes(judged)
                    continue
                # Content-aware resumability: the case changed since it was
                # classified (e.g. a model was re-run and now answers
                # differently), or its template or judged bytes are unknown.
                # Drop the stale verdict so the runner re-classifies it rather
                # than reusing the old label. The provenance sidecar describes
                # that verdict; a re-judge by the other runner must not
                # inherit it.
                verdict_path.unlink()
                (case_dir / "verdict.meta.json").unlink(missing_ok=True)
            prompt = render_case_prompt(case, template_version=template_version)
            prompt_path.write_bytes(prompt.encode("utf-8"))
    return cases


def _judged_prompt(case: AuditCase, case_dir: Path) -> bytes | None:
    """The prompt bytes a judged case's verdict stands on, or None when the
    case must be re-opened.

    The case is rendered on the version its sidecar records (absent: v1; a
    version it names no known one for gives None). Those bytes must be
    prompt.md's exactly, and, when the sidecar records ``prompt_sha256`` (the
    hash of the bytes its judge read), hash to it. Without prompt.md, that
    hash is the only evidence of what the judge read, so a sidecar without
    one gives None.
    """
    meta = _sidecar(case_dir)
    judged_on = recorded_template_version(meta)
    if judged_on is None:
        return None
    rendered = render_case_prompt(case, template_version=judged_on).encode("utf-8")
    recorded_sha256 = (meta or {}).get("prompt_sha256")
    if recorded_sha256 is not None and (
        recorded_sha256 != hashlib.sha256(rendered).hexdigest()
    ):
        return None
    prompt_path = case_dir / "prompt.md"
    if prompt_path.exists():
        return rendered if prompt_path.read_bytes() == rendered else None
    return rendered if recorded_sha256 is not None else None


def _sidecar(case_dir: Path) -> dict | None:
    """A case's ``verdict.meta.json``, or None when it has none.

    A sidecar that is not a JSON object records no template version.
    """
    path = case_dir / "verdict.meta.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text())
    except ValueError:
        meta = None
    return meta if isinstance(meta, dict) else {TEMPLATE_VERSION_FIELD: None}


def template_version_problems(audit_dir: Path) -> list[tuple[str, str]]:
    """Each judged case whose prompt and verdict disagree on the template.

    A tree may mix versions: a release's carried seeds keep the version they
    were judged on, while its new and re-opened cases use the one its driver
    names. Every verdict must have its prompt.md, its sidecar must name a
    known version (absent: v1), and prompt.md must begin with that version's
    header. Returns ``(case_id, problem)`` for each case that fails, in case
    order.
    """
    problems: list[tuple[str, str]] = []
    cases_root = audit_dir / "cases"
    if not cases_root.is_dir():
        return problems
    for case_dir in sorted(cases_root.iterdir()):
        if not (case_dir / "verdict.json").is_file():
            continue
        meta = _sidecar(case_dir)
        recorded = recorded_template_version(meta)
        prompt_path = case_dir / "prompt.md"
        if recorded is None:
            problem = (
                f"its sidecar's {TEMPLATE_VERSION_FIELD} "
                f"{meta.get(TEMPLATE_VERSION_FIELD)!r} names no template "
                f"version ({sorted(JUDGE_TEMPLATE_HEADERS)})"
            )
        elif not prompt_path.is_file():
            problem = "a verdict without prompt.md"
        else:
            actual = template_version_of(prompt_path.read_bytes())
            if actual == recorded:
                continue
            found = "no template version" if actual is None else f"v{actual}"
            problem = f"prompt.md is {found}, but its verdict records v{recorded}"
        problems.append((case_dir.name, problem))
    return problems


# --- Hedge detection -----------------------------------------------------------

# Published diagnoses must be definitive. These patterns catch the judge
# re-adjudicating the reference ("plausible", "not enough evidence") or
# hedging its own diagnosis — both mean the verdict answered the wrong
# question and must be re-judged, not shipped.
HEDGE_PATTERNS = (
    r"\bplausible\b",
    r"not enough (?:concrete )?evidence",
    r"insufficient (?:evidence|information)",
    r"\bcannot\s+(?:be\s+)?(?:determine|verify|confirm|rule|tell)",
    r"\bunable to (?:determine|verify|confirm|tell)",
    r"difficult to (?:verify|confirm|determine)",
    r"hard to (?:say|tell|verify)",
    r"reference (?:is|looks|seems|appears) "
    r"(?:plausible|correct|right|reasonable|accurate|sound|likely|fine)",
    r"call the .{0,60}reference wrong",
    r"treat the .{0,60}reference as",
    r"\bmay (?:be|have)\b",
    r"\bmight (?:be|have)\b",
    r"\bpossibly\b",
    r"\bperhaps\b",
    r"\bunclear\b",
)

_HEDGE_RE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)


def is_hedged(text: object) -> bool:
    """True when annotation text hedges instead of diagnosing."""
    return bool(_HEDGE_RE.search(str(text or "")))


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
        pass
    # Tolerate prose around the JSON: try decoding from each "{" until one
    # yields a complete object (handles a stray brace in leading prose).
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            return obj
        idx = text.find("{", idx + 1)
    return None


def _row_failure_source(meta: dict, model: str, requested_source: str) -> str:
    """Keep parse-contract labels scoped to genuinely missing predictions."""
    recorded_source = meta.get("recorded_failure_sources", {}).get(model)
    if recorded_source == "budget_exhausted_at_ceiling":
        return recorded_source
    source = validate_failure_source(requested_source)
    if source == "budget_exhausted_at_ceiling":
        if model in set(meta.get("missing_models", [])):
            return "parse_contract_failure"
        return "llm_error"
    if source == "parse_contract_failure" and model not in set(
        meta.get("missing_models", [])
    ):
        return "llm_error"
    return source


def collect_audit(country_dir: Path, audit_dir: Path) -> dict[str, pd.DataFrame]:
    """Fold verdicts into the annotation schema.

    Returns ``{"row": ..., "case": ..., "missing": ..., "hedged": ...,
    "template": ...}``.
    ``row`` and ``case`` match the committed annotation CSV columns, extended
    with ``rationale`` and ``reference_suspect`` so the classifier's reasoning
    is preserved. ``missing`` lists cases whose verdict has not yet been
    produced (resumability). ``hedged`` lists case ids whose diagnosis or
    rationale hedges instead of diagnosing (see :data:`HEDGE_PATTERNS`) —
    delete those ``verdict.json`` files and re-run the classifier rather than
    shipping them. ``template`` lists the judged cases whose prompt and
    verdict disagree on the judge template version
    (:func:`template_version_problems`).
    """
    manifest = _load_manifest(audit_dir)
    cases_root = audit_dir / "cases"
    country = country_dir.name

    row_records: list[dict] = []
    case_records: list[dict] = []
    missing: list[str] = []
    hedged: list[str] = []

    for case_id, meta in manifest.items():
        if meta.get("parse_failure_only"):
            # Every wrong model simply returned no value — a parse failure, not
            # a substantive error. Classified deterministically, no classifier.
            note = "All wrong responses were missing or unparseable predictions."
            row_sources = []
            for model in meta["wrong_models"]:
                failure_source = meta.get("recorded_failure_sources", {}).get(
                    model,
                    "parse_contract_failure",
                )
                row_sources.append(failure_source)
                row_records.append(
                    {
                        "country": country,
                        "scenario_id": meta["scenario_id"],
                        "variable": meta["variable"],
                        "model": model,
                        "failure_source": failure_source,
                        "failure_subtype": "missing_output",
                        "reference_suspect": False,
                        "annotation": note,
                    }
                )
            case_records.append(
                {
                    "country": country,
                    "scenario_id": meta["scenario_id"],
                    "variable": meta["variable"],
                    "wrong_model_count": len(meta["wrong_models"]),
                    "case_failure_source": (
                        row_sources[0]
                        if len(set(row_sources)) == 1
                        else "parse_contract_failure"
                    ),
                    "case_failure_subtype": "missing_output",
                    "reference_suspect": False,
                    "reference_bug_hypothesis": "",
                    "case_annotation": note,
                }
            )
            continue
        verdict = parse_verdict(cases_root / case_id / "verdict.json")
        if verdict is None:
            missing.append(case_id)
            continue
        case_source = validate_failure_source(verdict["case_failure_source"])
        recorded_sources = set(meta.get("recorded_failure_sources", {}).values())
        if (
            case_source == "budget_exhausted_at_ceiling"
            and "budget_exhausted_at_ceiling" not in recorded_sources
        ):
            wrong_models = set(meta.get("wrong_models", []))
            missing_models = set(meta.get("missing_models", []))
            case_source = (
                "parse_contract_failure"
                if wrong_models and wrong_models <= missing_models
                else "llm_error"
            )
        case_subtype = validate_failure_subtype(verdict["case_failure_subtype"])
        reference_suspect = bool(verdict.get("reference_suspect"))
        rationale = str(verdict.get("rationale", "")).strip()
        per_model = {
            str(m["model"]): m for m in verdict.get("models", []) if m.get("model")
        }
        case_hedged = is_hedged(rationale)
        for model in meta["wrong_models"]:
            entry = per_model.get(model, {})
            # The published per-model annotation is the model-specific
            # diagnosis; the case rationale is only a fallback for verdicts
            # predating the diagnosis field.
            diagnosis = str(entry.get("diagnosis", "")).strip() or rationale
            case_hedged = case_hedged or is_hedged(diagnosis)
            row_records.append(
                {
                    "country": country,
                    "scenario_id": meta["scenario_id"],
                    "variable": meta["variable"],
                    "model": model,
                    "failure_source": _row_failure_source(
                        meta,
                        model,
                        entry.get("failure_source", case_source),
                    ),
                    "failure_subtype": validate_failure_subtype(
                        entry.get("failure_subtype", case_subtype)
                    ),
                    "reference_suspect": reference_suspect,
                    "annotation": diagnosis,
                }
            )
        if case_hedged:
            hedged.append(case_id)
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
    # Explicit columns so empty output still carries the header contract.
    row_columns = [
        "country",
        "scenario_id",
        "variable",
        "model",
        "failure_source",
        "failure_subtype",
        "reference_suspect",
        "annotation",
    ]
    case_columns = [
        "country",
        "scenario_id",
        "variable",
        "wrong_model_count",
        "case_failure_source",
        "case_failure_subtype",
        "reference_suspect",
        "reference_bug_hypothesis",
        "case_annotation",
    ]
    return {
        "row": pd.DataFrame(row_records, columns=row_columns),
        "case": pd.DataFrame(case_records, columns=case_columns),
        "missing": pd.DataFrame({"case_id": missing}, columns=["case_id"]),
        "hedged": pd.DataFrame({"case_id": hedged}, columns=["case_id"]),
        "template": pd.DataFrame(
            template_version_problems(audit_dir), columns=["case_id", "problem"]
        ),
    }
