"""Reference adversary: a law-first judge that attacks consensus-flagged references.

The diagnosis judge in :mod:`policybench.audit` explains why models missed the
reference and is told to treat the reference as correct. That design cannot
catch a wrong reference unless the judge already knows the contradicting law.
The reference adversary does the opposite job. It takes the cells that
:mod:`policybench.consensus` flags (many models, or several of the strongest,
agreeing on one answer other than the reference) and tries to show from
primary law that the reference is wrong.

Each case runs in two mechanically separated stages:

1. Law first. The judge sees the exact household prompt the models saw, the
   output's definition, the reference value and the consensus answers with
   each member model's explanation, but not how the engine derived the
   reference. It works the answer from primary law in force for the tax year,
   cites every rule, and says which answer the law supports. It may use web
   search and fetch but not PolicyEngine, PolicyBench or their repositories
   (:data:`BLOCKED_DOMAINS`).
2. Reconcile. A fresh call sees everything from stage 1, the stage-1 result
   verbatim with its sha256, and only now the engine derivation. Stage 1 is
   frozen: if the derivation shows stage 1 erred, the judge must say so in
   ``stage1_error`` rather than silently change course. It returns a verdict
   (:data:`VERDICTS`) and a suggested developer adjudication.

This module owns the deterministic parts: assembling cases from a frozen
dashboard payload and a consensus-flags report (``build_adversary_cases``),
writing prompts with content-aware resumability (``prepare_adversary``,
``write_stage2_prompt``), validating and publishing judge outputs and their
provenance sidecars (the ``finalize`` command the runners call), and folding
verdicts into a table, a cross-judge comparison and a developer adjudication
queue in the case-notes schema (``collect_adversary``, ``merge_judges``,
``adjudication_queue``, ``apply_adversary_flags``). The runners
``scripts/run_reference_adversary_claude.sh`` and
``scripts/run_reference_adversary_codex.sh`` make the judge calls.

A verdict never changes a score or a reference. A case whose verdict is not
``reference_holds`` goes to developer adjudication through the existing
``reference_suspect`` flag, which blocks a snapshot freeze until a developer
records a ``reference_verdict`` (:mod:`policybench.adjudications`). Nothing
here reads a score field or writes a prediction.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import math
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from policybench.config import TAX_YEAR

if TYPE_CHECKING:
    import pandas as pd

# The date the frozen references' law was cut off: the convention module
# reference_audit/2026-09-28/fixes/latest_final.py encodes law published before
# this date.
REFERENCE_FREEZE = "2026-07-03"

VERDICTS = (
    "reference_holds",
    "reference_wrong",
    "definition_mismatch",
    "prompt_ambiguous",
)
LAW_SUPPORTS = ("reference", "consensus", "neither", "both_readings")
CONFIDENCES = ("high", "medium", "low")
SUGGESTED_ADJUDICATIONS = (
    "affirmed",
    "regenerated",
    "engine_defect",
    "unlisted_input",
    "later_law",
    "definition_exclusion",
    "none",
)
# The suggestions each verdict may carry ("none" goes with any verdict). The
# stage-2 prompt states these pairings; collect_adversary reports a verdict
# that breaks them as inconsistent.
VERDICT_SUGGESTIONS = {
    "reference_holds": ("affirmed", "none"),
    "reference_wrong": ("engine_defect", "later_law", "regenerated", "none"),
    "definition_mismatch": ("definition_exclusion", "regenerated", "none"),
    "prompt_ambiguous": ("unlisted_input", "definition_exclusion", "none"),
}
BLOCKED_DOMAINS = (
    "policybench.org",
    "www.policybench.org",
    "policyengine.org",
    "www.policyengine.org",
    "github.com",
    "raw.githubusercontent.com",
)
# A URL, citation source or search query naming either of these reaches for
# the engine or the benchmark, whatever the host.
BLOCKED_NAMES = ("policyengine", "policybench")
# Strings whose appearance in a codex judge's tool activity (a shell command,
# its output, a search query or an opened URL) means the judge reached for
# engine-derived material: the derivations this module writes, the frozen
# annotations, the dashboard payload, another judge's outputs, or the engine
# and benchmark themselves. Matched case-insensitively.
DERIVATION_MARKERS = (
    "derivations/",
    "us_case_reference_explanations",
    "case_reference_explanations",
    "data.json",
    "referenceexplanation",
    "stage2_prompt",
    "stage1.json",
    "verdict.json",
    "case_notes.csv",
    "audit_row_annotations",
    "adjudications.json",
    "policybench",
    "policyengine",
)
# The judge's tools under the Claude runner (the CLI adds StructuredOutput for
# --json-schema). Claude Code's WebSearch and WebFetch tools.
CLAUDE_ALLOWED_TOOLS = ("WebSearch", "WebFetch")
# Codex event item types that carry no tool activity, and those whose tool
# activity the audit inspects. Any other item type is reported.
CODEX_QUIET_ITEMS = ("agent_message", "reasoning", "todo_list", "error")
CODEX_AUDITED_ITEMS = ("command_execution", "web_search")
RUNNERS = {
    "claude": "scripts/run_reference_adversary_claude.sh",
    "codex": "scripts/run_reference_adversary_codex.sh",
}
# Each runner's blinding of stage 1: the Claude judge has no file tools; the
# Codex judge runs from an empty directory and its event log is audited.
BLINDING = {"claude": "tools", "codex": "cwd+log-audit"}

STAGE1_FILE = "stage1.json"
STAGE1_META = "stage1.meta.json"
STAGE1_PROMPT = "stage1_prompt.md"
STAGE2_PROMPT = "stage2_prompt.md"
VERDICT_FILE = "verdict.json"
VERDICT_META = "verdict.meta.json"
STAGE1_SCHEMA_FILE = "schema_stage1.json"
VERDICT_SCHEMA_FILE = "schema_verdict.json"
# Values within this many dollars count as the same answer when collect checks
# a verdict against its case and its stage 1 (the consensus trigger's default
# tolerance).
VALUE_TOLERANCE = 1.0


# --- Output contracts ----------------------------------------------------------

CITATION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source": {
            "type": "string",
            "description": "The statute, regulation, publication, form or "
            "instructions, named as its issuer names it.",
        },
        "pinpoint": {
            "type": "string",
            "description": "Section, subsection, line, table or page.",
        },
        "url": {"type": "string", "description": "The URL you read."},
        "published": {
            "type": "string",
            "description": "Publication or effective date as the source "
            "states it (YYYY-MM-DD where known).",
        },
        "pre_freeze": {
            "type": ["boolean", "null"],
            "description": f"True if published before {REFERENCE_FREEZE}, "
            "false if after, null if unknown.",
        },
        "quote": {
            "type": "string",
            "description": "A short verbatim quote of the rule relied on.",
        },
    },
    "required": ["source", "pinpoint", "url", "published", "pre_freeze", "quote"],
}

STAGE1_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "independent_answer": {
            "type": ["number", "null"],
            "description": "Your own answer from the law (1 or 0 for an "
            "eligibility output); null only if the law leaves it undetermined "
            "on the stated facts.",
        },
        "computation": {
            "type": "string",
            "description": "Your step-by-step computation from the stated "
            "facts, naming the rule behind each step.",
        },
        "citations": {"type": "array", "minItems": 1, "items": CITATION_SCHEMA},
        "law_supports": {"type": "string", "enum": list(LAW_SUPPORTS)},
        "definition_reading": {
            "type": "string",
            "description": "How you read the output definition for this household.",
        },
        "ambiguity": {
            "type": "string",
            "description": "A second reading the definition or prompt "
            'genuinely admits and the answer it gives; "" if none.',
        },
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
    },
    "required": [
        "independent_answer",
        "computation",
        "citations",
        "law_supports",
        "definition_reading",
        "ambiguity",
        "confidence",
    ],
}

VERDICT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "summary": {
            "type": "string",
            "description": "2-4 sentences: what the law gives, what the "
            "engine did, and why the verdict follows.",
        },
        "independent_answer": {"type": ["number", "null"]},
        "reference_value": {"type": "number"},
        "consensus_value": {"type": ["number", "null"]},
        "engine_step_at_issue": {
            "type": "string",
            "description": "The derivation step that departs from the law or "
            'the definition; "" when the reference holds.',
        },
        "stage1_error": {
            "type": "string",
            "description": 'Where stage 1 erred and why; "" if stage 1 stands.',
        },
        "citations": {"type": "array", "minItems": 1, "items": CITATION_SCHEMA},
        "suggested_adjudication": {
            "type": "string",
            "enum": list(SUGGESTED_ADJUDICATIONS),
        },
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
    },
    "required": [
        "verdict",
        "summary",
        "independent_answer",
        "reference_value",
        "consensus_value",
        "engine_step_at_issue",
        "stage1_error",
        "citations",
        "suggested_adjudication",
        "confidence",
    ],
}


def canonical_json(document: Any) -> str:
    """The one serialization of a judge output this module writes and hashes."""
    return json.dumps(document, indent=2, sort_keys=True)


def sha256_text(text: str) -> str:
    """The sha256 of a string's UTF-8 bytes, as lowercase hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blocked_url(url: str) -> bool:
    """Whether a URL is on a blocked domain (or a subdomain) or names the engine."""
    text = str(url or "").strip()
    if not text:
        return False
    if any(name in text.lower() for name in BLOCKED_NAMES):
        return True
    try:
        host = urlsplit(text if "//" in text else f"//{text}").hostname or ""
    except ValueError:
        return False
    host = host.lower().rstrip(".")
    return any(
        host == domain or host.endswith(f".{domain}") for domain in BLOCKED_DOMAINS
    )


_URL = re.compile(r"https?://[^\s\"'<>()\[\]{}\\]+", re.IGNORECASE)


def _result_text(content: Any) -> str:
    """The text of a tool result's content: a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            _result_text(block.get("text", block.get("content")))
            if isinstance(block, dict)
            else str(block)
            for block in content
        )
    return "" if content is None else json.dumps(content)


def blocked_search_result(text: str) -> list[str]:
    """What in a search result reaches for the engine or the benchmark.

    Each URL the result lists on a blocked domain or naming either (in order,
    without repeats), and "text names <name>" when the result's text names one
    outside such a URL. Empty for a clean result.
    """
    found: list[str] = []
    for url in _URL.findall(text or ""):
        url = url.rstrip(".,;:")
        if blocked_url(url) and url not in found:
            found.append(url)
    remainder = _URL.sub(" ", text or "").lower()
    found.extend(f"text names {name}" for name in BLOCKED_NAMES if name in remainder)
    return found


def blocked_citation_errors(document: Any) -> list[str]:
    """Citations that point at a source the adversary may not consult."""
    if not isinstance(document, dict) or not isinstance(
        document.get("citations"), list
    ):
        return []
    errors = []
    for index, citation in enumerate(document["citations"]):
        if not isinstance(citation, dict):
            continue
        url = str(citation.get("url") or "")
        source = str(citation.get("source") or "")
        if blocked_url(url) or any(name in source.lower() for name in BLOCKED_NAMES):
            errors.append(
                f"citations/{index}: cites a blocked source ({source!r}, {url!r})"
            )
    return errors


def output_errors(schema: dict, document: Any) -> list[str]:
    """Schema violations of a judge output plus citations of blocked sources."""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "judge outputs are validated with jsonschema; install it (uv sync "
            "--extra dev) to prepare, collect or finalize adversary cases"
        ) from exc
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(document)
    )
    return errors + blocked_citation_errors(document)


def _read_output(path: Path, schema: dict) -> tuple[dict | None, str, list[str]]:
    """A judge output file: (document if valid, sha256 of its bytes, errors)."""
    if not path.is_file():
        return None, "", ["absent"]
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, digest, [f"not JSON: {exc}"]
    errors = output_errors(schema, document)
    return (None if errors else document), digest, errors


def bound_sidecar(output_path: Path, meta_path: Path) -> dict | None:
    """The provenance sidecar if it describes the output's current bytes.

    A sidecar whose ``output_sha256`` does not match the output it sits beside
    is stale (the output was re-judged or edited) and carries no provenance.
    """
    if not output_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    if meta.get("output_sha256") != _sha256_file(output_path):
        return None
    return meta


# --- Cases ---------------------------------------------------------------------


@dataclass(frozen=True)
class AdversaryCase:
    """One consensus-flagged ``(scenario_id, variable)`` cell to attack.

    ``consensus`` holds the triggering clusters, each a dict with the
    cluster's ``answer``, ``n_models``, ``n_top``, ``top_models`` and
    ``members`` (each member's ``model``, raw ``prediction`` and
    ``explanation``). ``derivation`` is the engine's derivation of the
    reference; it is shown only in stage 2 and never written to the manifest.
    """

    case_id: str
    country: str
    scenario_id: str
    variable: str
    definition: str
    household_prompt: str
    reference_value: float
    consensus: tuple[dict, ...]
    models_answered: int
    models_exact: int
    derivation: str
    spec_id: str = ""
    metric_type: str = "amount"
    state: str = ""
    trigger: tuple[str, ...] = ()

    def to_manifest_row(self) -> dict:
        """The case as a ``cases.jsonl`` row, without the derivation."""
        row = asdict(self)
        derivation = row.pop("derivation")
        row["consensus"] = [dict(cluster) for cluster in self.consensus]
        row["trigger"] = list(self.trigger)
        row["derivation_sha256"] = sha256_text(derivation) if derivation else None
        return row

    @classmethod
    def from_manifest_row(cls, row: dict, derivation: str) -> AdversaryCase:
        """Rebuild a case from its manifest row and its derivation file."""
        return cls(
            case_id=str(row["case_id"]),
            country=str(row["country"]),
            scenario_id=str(row["scenario_id"]),
            variable=str(row["variable"]),
            definition=str(row["definition"]),
            household_prompt=str(row["household_prompt"]),
            reference_value=float(row["reference_value"]),
            consensus=tuple(dict(cluster) for cluster in row["consensus"]),
            models_answered=int(row["models_answered"]),
            models_exact=int(row["models_exact"]),
            derivation=derivation,
            spec_id=str(row.get("spec_id", "")),
            metric_type=str(row.get("metric_type", "amount")),
            state=str(row.get("state", "") or ""),
            trigger=tuple(row.get("trigger", ())),
        )


def _case_id(country: str, scenario_id: str, variable: str) -> str:
    """Filesystem-safe case id; the same rule as ``policybench.audit._case_id``."""
    safe = f"{country}__{scenario_id}__{variable}"
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in safe)


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def load_derivations(
    annotations_dir: Path | str, country: str = "us"
) -> dict[tuple[str, str], str]:
    """Map ``(scenario_id, variable)`` to the frozen engine derivation.

    Reads ``<country>_case_reference_explanations.csv`` (columns country,
    scenario_id, variable, reference_value, trace_lines, explanation, error)
    from a frozen annotations directory. Rows with an empty explanation are
    skipped, so the caller falls back to the payload's ``referenceExplanation``
    for them.
    """
    import pandas as pd

    path = Path(annotations_dir) / f"{country}_case_reference_explanations.csv"
    if not path.is_file():
        raise FileNotFoundError(f"no reference explanations at {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = {"scenario_id", "variable", "explanation"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if "country" in frame.columns:
        frame = frame[frame["country"].astype(str) == country]
    derivations: dict[tuple[str, str], str] = {}
    for row in frame.itertuples(index=False):
        text = _clean(row.explanation)
        key = (str(row.scenario_id), str(row.variable))
        if text and key not in derivations:
            derivations[key] = text
    return derivations


def _number(value: float) -> str:
    """A number as the judge reads it: thousands separators, no float noise."""
    if isinstance(value, bool):
        return str(int(value))
    try:
        decimal = Decimal(repr(float(value)))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if decimal == decimal.to_integral_value():
        return f"{int(decimal):,}"
    return format(decimal, ",")


def _truncate(text: str, limit: int) -> str:
    if limit < 0 or len(text) <= limit:
        return text
    return f"{text[:limit]} [... {len(text) - limit} more characters cut]"


def _cell_reference(cell: dict) -> float:
    references = {json.dumps(entry.get("groundTruth")) for entry in cell.values()}
    if len(references) != 1:
        raise ValueError("models disagree on groundTruth")
    value = next(iter(cell.values())).get("groundTruth")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"no numeric groundTruth: {value!r}")
    return float(value)


def _payload_derivation(cell: dict) -> str:
    for model in sorted(cell):
        text = _clean(cell[model].get("referenceExplanation"))
        if text:
            return text
    return ""


def build_adversary_cases(
    payload: dict,
    flags: list[dict],
    *,
    derivations: dict | None = None,
    max_explanation_chars: int = 2000,
) -> list[AdversaryCase]:
    """One :class:`AdversaryCase` per consensus flag.

    ``payload`` is a US dashboard payload (``policybench.consensus.
    load_us_payload``) and ``flags`` the ``flags`` list of a consensus-flags
    report computed from it. From each flagged cell the case takes the exact
    household prompt the models saw (``scenarios[sid].prompt.tool``), the
    output's definition as the prompt rendered it, the reference value, and
    each triggering cluster's members with their raw prediction and
    explanation (cut to ``max_explanation_chars``). It reads no score field and
    no annotation. ``derivations`` maps ``(scenario_id, variable)`` to the
    engine derivation (``load_derivations``); a cell it does not cover falls
    back to the payload's ``referenceExplanation``.

    Raises ``ValueError`` when a flag does not match the payload (another
    payload's reference or predictions, a missing scenario or model) or when
    a cell is flagged twice.
    """
    from policybench.prompts import get_variable_description
    from policybench.spec import metric_type_for_output, output_group_id

    country = str(payload.get("country") or "us")
    scenarios = payload.get("scenarios") or {}
    predictions = payload.get("scenarioPredictions") or {}
    cases: list[AdversaryCase] = []
    seen: set[tuple[str, str]] = set()
    for flag in flags:
        scenario_id = str(flag["scenario_id"])
        variable = str(flag["variable"])
        where = f"{scenario_id} {variable}"
        if (scenario_id, variable) in seen:
            raise ValueError(f"{where}: flagged more than once")
        seen.add((scenario_id, variable))
        scenario = scenarios.get(scenario_id)
        if not isinstance(scenario, dict):
            raise ValueError(f"{where}: scenario missing from the payload")
        household_prompt = ((scenario.get("prompt") or {}).get("tool")) or ""
        if not household_prompt:
            raise ValueError(f"{where}: the payload has no tool prompt")
        cell = (predictions.get(scenario_id) or {}).get(variable)
        if not cell:
            raise ValueError(f"{where}: no predictions in the payload")
        try:
            reference = _cell_reference(cell)
        except ValueError as exc:
            raise ValueError(f"{where}: {exc}") from exc
        if float(flag["reference"]) != reference:
            raise ValueError(
                f"{where}: the flag's reference {flag['reference']!r} is not the "
                f"payload's {reference!r} (flags from another payload?)"
            )
        clusters = []
        for cluster in flag["clusters"]:
            members = []
            flagged = cluster.get("predictions") or {}
            for model in cluster["models"]:
                entry = cell.get(model)
                if not isinstance(entry, dict):
                    raise ValueError(f"{where}: model {model} has no prediction")
                prediction = entry.get("prediction")
                if model in flagged and (
                    not isinstance(prediction, (int, float))
                    or float(prediction) != float(flagged[model])
                ):
                    raise ValueError(
                        f"{where}: {model}'s prediction {prediction!r} is not the "
                        f"flag's {flagged[model]!r} (flags from another payload?)"
                    )
                members.append(
                    {
                        "model": str(model),
                        "prediction": prediction,
                        "explanation": _truncate(
                            _clean(entry.get("explanation")), max_explanation_chars
                        ),
                    }
                )
            clusters.append(
                {
                    "answer": float(cluster["answer"]),
                    "n_models": int(cluster["n_models"]),
                    "n_top": int(cluster.get("n_top", 0)),
                    "top_models": list(cluster.get("top_models", [])),
                    "members": members,
                }
            )
        derivation = ""
        if derivations is not None:
            derivation = _clean(derivations.get((scenario_id, variable)))
        if not derivation:
            derivation = _payload_derivation(cell)
        cases.append(
            AdversaryCase(
                case_id=_case_id(country, scenario_id, variable),
                country=country,
                scenario_id=scenario_id,
                variable=variable,
                definition=get_variable_description(variable, country=country),
                household_prompt=household_prompt,
                reference_value=reference,
                consensus=tuple(clusters),
                models_answered=int(flag["models_answered"]),
                models_exact=int(flag["models_exact"]),
                derivation=derivation,
                spec_id=output_group_id(variable),
                metric_type=metric_type_for_output(variable),
                state=_clean(flag.get("state") or scenario.get("state")),
                trigger=tuple(str(t) for t in flag.get("trigger", ())),
            )
        )
    return cases


# --- Prompts -------------------------------------------------------------------

_DOMAINS = ", ".join(BLOCKED_DOMAINS)

_SOURCE_RULES = f"""\
Do not consult PolicyEngine or PolicyBench in any form: not policyengine.org, \
policybench.org, their GitHub repositories, their documentation, their \
package source, or any calculator built on them. Do not fetch anything from \
these domains: {_DOMAINS}. When your search tool accepts domains to exclude \
(blocked_domains), pass all of these domains on every search, so that no \
result comes from them: a search whose results list or name PolicyEngine or \
PolicyBench voids your answer. Do not rely on any calculator or estimate \
built by an AI model. A citation of any of these sources voids your answer."""

_STAGE1_HEADER = f"""\
You are a reference adversary for a US tax-and-benefit benchmark. Each \
benchmark question gives a household and asks for policy quantities for tax \
year {TAX_YEAR}. A microsimulation engine produced the reference answer. On \
the question below, a cluster of AI models answering from memory, without \
tools, agreed on an answer other than the reference. Agreement among models \
proves nothing, and neither does the engine. Your job is to find out what the \
law gives.

This is stage 1 of 2. In this stage you work the answer out yourself from \
primary law, before you see anything about how the engine computed its value.

How to work:
1. Use web search and web fetch to find and read primary law in force for tax \
year {TAX_YEAR}: statutes, regulations, official agency publications, and \
official forms and their instructions. Prefer the issuing government's own \
site.
2. Apply the household prompt's conventions exactly as the models were told \
them: treat any unlisted numeric input as 0 and any other unlisted fact, \
boolean or status as false; assume tax filing and program take-up when \
required; do not infer unlisted income, expenses, assets, benefit receipt, \
rent or health coverage.
3. Read the output definition literally. It decides which people, tax units, \
returns, taxes, credits or benefits the number covers. Where it lists \
components, decide for each candidate amount whether the definition includes \
it. Where the household holds more than one tax unit or return, decide from \
the definition which of them the number covers.
4. Cite every rule you rely on: the source, a pinpoint (section, line, table \
or page), the URL you read, the publication or effective date, and a short \
verbatim quote. The reference's law was frozen on {REFERENCE_FREEZE}: set \
pre_freeze to true if the source was published before that date, false if \
after, and null if you cannot tell. If an amount for {TAX_YEAR} (a standard \
deduction, bracket, threshold, rate base or allotment) had not been published \
before {REFERENCE_FREEZE}, say so in computation and say what had been \
published.
5. {_SOURCE_RULES}
6. Say which answer the law supports: "reference", "consensus", "neither", or \
"both_readings" (the reference under one reasonable reading of the definition \
or the facts, the consensus under another).
7. In definition_reading, say how you read the output definition for this \
household. In ambiguity, describe any second reading that the definition or \
the household prompt genuinely admits, and the answer it gives; use "" if \
there is none.
8. independent_answer is your own number (1 or 0 for an eligibility output). \
Use null only when the stated facts and the law leave it genuinely \
undetermined, and say why in ambiguity.

Some output definitions mention PolicyEngine (for example "eligible for \
Medicaid under PolicyEngine rules"). Work those from the law as well; if the \
mention could change the answer, say so in ambiguity.

Return only the JSON object the schema asks for."""

_STAGE2_HEADER = f"""\
You are a reference adversary for a US tax-and-benefit benchmark. Each \
benchmark question gives a household and asks for policy quantities for tax \
year {TAX_YEAR}. A microsimulation engine produced the reference answer. On \
the question below, a cluster of AI models answering from memory, without \
tools, agreed on an answer other than the reference.

This is stage 2 of 2: reconciliation. In stage 1, a judge who had not seen \
how the engine derived the reference worked the question from primary law. \
Its result appears below exactly as it was recorded, with its sha256. Stage 1 \
is frozen and you may not revise it. If the engine derivation or the law \
shows that stage 1 erred (it misread a fact, missed or misapplied a rule, or \
used the wrong year's amount), say so in stage1_error and name the error. Do \
not silently change course: if your independent_answer, or your view of which \
answer the law supports, differs from stage 1's, stage1_error must say why. \
Use "" for stage1_error only when stage 1 stands.

Only now do you see how the engine derived the reference. The derivation is a \
short narrative that a language model wrote from the engine's computation \
trace for this household; it can misdescribe a step, but the reference value \
is the engine's own output. Compare each step with the law and with the \
output definition, and decide:
- reference_holds: the reference is what the law and the output definition \
give on the stated facts.
- reference_wrong: the engine misapplies the law on the stated facts, or \
uses an amount or rule the law had not published (for example a {TAX_YEAR} \
amount the engine projected itself where no agency had published one before \
{REFERENCE_FREEZE}).
- definition_mismatch: the engine computes something other than what the \
output definition describes (it includes or leaves out people, returns, \
taxes, credits or benefits that the definition covers or excludes).
- prompt_ambiguous: the stated facts or the definition genuinely admit more \
than one answer (for example the answer turns on an input the prompt does not \
list).

engine_step_at_issue names the derivation step that departs from the law or \
the definition; use "" when the reference holds.

suggested_adjudication:
- affirmed: the reference holds.
- regenerated: the reference should be recomputed under a stated convention \
or a corrected input; the output stays scored.
- engine_defect: the engine misapplies the law on the stated facts.
- unlisted_input: the answer turns on an input the prompt does not list.
- later_law: the reference rests on law or an amount published after \
{REFERENCE_FREEZE}, or never published.
- definition_exclusion: the engine's quantity does not match the output \
definition, so the output should be excluded.
- none: you suggest nothing.
Pair them this way: reference_holds with affirmed; reference_wrong with \
engine_defect, later_law or regenerated; definition_mismatch with \
definition_exclusion or regenerated; prompt_ambiguous with unlisted_input or \
definition_exclusion. "none" goes with any verdict.

reference_value is the engine reference below. consensus_value is the \
consensus answer you weighed (null if none applies).

Cite the law you rely on as in stage 1: source, pinpoint, URL, date, \
pre_freeze and a short quote. The engine derivation is not a citation. \
{_SOURCE_RULES}

Your verdict changes no score. A developer adjudicates every case you do not \
return as reference_holds.

Return only the JSON object the schema asks for."""


def _block(title: str, text: str) -> str:
    return f"----- BEGIN {title} -----\n{text}\n----- END {title} -----"


def _reference_text(case: AdversaryCase) -> str:
    value = case.reference_value
    if case.metric_type == "binary":
        return f"{_number(value)} ({'eligible' if value else 'not eligible'})"
    rounded = f"${value:,.2f}"
    if round(value, 2) == value:
        return rounded
    return f"{rounded} (engine output {_number(value)})"


def _case_sections(case: AdversaryCase) -> list[str]:
    """The case as both stages show it; never the derivation."""
    kind = (
        "an eligibility flag, 1 or 0"
        if case.metric_type == "binary"
        else "an annual dollar amount"
    )
    lines = [
        f"TAX YEAR: {TAX_YEAR}    REFERENCE LAW FROZEN: {REFERENCE_FREEZE}",
        f"STATE: {case.state or 'see the household prompt'}",
        f"OUTPUT: {case.variable} ({kind})",
        f"OUTPUT DEFINITION, as the models saw it: {case.definition}",
        "",
        "HOUSEHOLD PROMPT SHOWN TO THE MODELS (verbatim; it asks for several "
        f"outputs, and this case concerns only {case.variable}):",
        _block("HOUSEHOLD PROMPT", case.household_prompt),
        "",
        f"ENGINE REFERENCE VALUE: {_reference_text(case)}",
        f"MODELS: {case.models_answered} gave a usable answer; "
        f"{case.models_exact} matched the reference.",
        "",
        "CONSENSUS ANSWERS (clusters of models agreeing on a value other than "
        "the reference):",
    ]
    for number, cluster in enumerate(case.consensus, 1):
        lines.append(
            f"\nCluster {number}: {_number(cluster['answer'])}, given by "
            f"{cluster['n_models']} models ({cluster.get('n_top', 0)} of them "
            "among the benchmark's top-ranked models)"
        )
        for member in cluster["members"]:
            explanation = member.get("explanation") or "(no explanation given)"
            lines.append(
                f"- {member['model']}: answered {_number(member['prediction'])}\n"
                f"  explanation: {explanation}"
            )
    return lines


def render_stage1_prompt(case: AdversaryCase) -> str:
    """The law-first prompt: everything about the case except the derivation."""
    return "\n".join([_STAGE1_HEADER, "", *_case_sections(case)])


def render_stage2_prompt(case: AdversaryCase, stage1: dict, stage1_sha256: str) -> str:
    """The reconciling prompt: the case, frozen stage 1, then the derivation.

    ``stage1`` is embedded as :func:`canonical_json`, the form the runners
    publish ``stage1.json`` in, so the embedded text is the stage-1 file and
    ``stage1_sha256`` is the sha256 of exactly that text.
    """
    derivation = case.derivation or "(no derivation was recorded for this case)"
    return "\n".join(
        [
            _STAGE2_HEADER,
            "",
            *_case_sections(case),
            "",
            f"STAGE 1 RESULT (frozen; sha256 {stage1_sha256}):",
            _block("STAGE 1 RESULT", canonical_json(stage1)),
            "",
            "ENGINE DERIVATION OF THE REFERENCE:",
            _block("ENGINE DERIVATION", derivation),
        ]
    )


# --- Preparation and resumability ---------------------------------------------

_STAGE1_OUTPUTS = (STAGE1_FILE, STAGE1_META)
_STAGE2_OUTPUTS = (STAGE2_PROMPT, VERDICT_FILE, VERDICT_META)


def _unlink(case_dir: Path, names: tuple[str, ...]) -> None:
    for name in names:
        (case_dir / name).unlink(missing_ok=True)


def prepare_adversary(
    adversary_dir: Path | str, cases: list[AdversaryCase]
) -> list[AdversaryCase]:
    """Write the schemas, the manifest, stage-1 prompts and derivations.

    Layout under ``adversary_dir``::

        schema_stage1.json
        schema_verdict.json
        cases.jsonl                         (manifest; no derivation)
        derivations/<case_id>.md            (stage-2 input, outside the case dir)
        cases/<case_id>/stage1_prompt.md
        cases/<case_id>/stage1.json         (written later by a runner)
        cases/<case_id>/stage2_prompt.md    (written by write_stage2_prompt)
        cases/<case_id>/verdict.json        (written later by a runner)

    Resumable and content-aware: a case whose stage-1 prompt changed loses its
    stage-1 output, stage-2 prompt, verdict and their sidecars; a case whose
    derivation changed loses its stage-2 prompt and verdict but keeps stage 1,
    which never saw the derivation. Case directories and derivations of cases
    no longer listed are removed.
    """
    adversary_dir = Path(adversary_dir)
    ids = [case.case_id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate adversary cases: {duplicates}")
    adversary_dir.mkdir(parents=True, exist_ok=True)
    (adversary_dir / STAGE1_SCHEMA_FILE).write_text(
        json.dumps(STAGE1_SCHEMA, indent=2) + "\n"
    )
    (adversary_dir / VERDICT_SCHEMA_FILE).write_text(
        json.dumps(VERDICT_SCHEMA, indent=2) + "\n"
    )
    cases_root = adversary_dir / "cases"
    derivations_root = adversary_dir / "derivations"
    cases_root.mkdir(exist_ok=True)
    derivations_root.mkdir(exist_ok=True)
    current = set(ids)
    for child in cases_root.iterdir():
        if child.is_dir() and child.name not in current:
            shutil.rmtree(child)
    for child in derivations_root.iterdir():
        if child.is_file() and child.suffix == ".md" and child.stem not in current:
            child.unlink()
    with (adversary_dir / "cases.jsonl").open("w") as manifest:
        for case in cases:
            manifest.write(json.dumps(case.to_manifest_row()) + "\n")
            case_dir = cases_root / case.case_id
            case_dir.mkdir(exist_ok=True)
            prompt_path = case_dir / STAGE1_PROMPT
            new_prompt = render_stage1_prompt(case)
            if not prompt_path.is_file() or prompt_path.read_text() != new_prompt:
                # Stage 1 (and everything built on it) answered another prompt.
                _unlink(case_dir, _STAGE1_OUTPUTS + _STAGE2_OUTPUTS)
            prompt_path.write_text(new_prompt)
            derivation_path = derivations_root / f"{case.case_id}.md"
            if (
                not derivation_path.is_file()
                or derivation_path.read_text() != case.derivation
            ):
                # Stage 2 reconciled against another derivation; stage 1 never
                # saw it and stands.
                _unlink(case_dir, _STAGE2_OUTPUTS)
            derivation_path.write_text(case.derivation)
    return cases


def _load_manifest(adversary_dir: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    manifest = Path(adversary_dir) / "cases.jsonl"
    if manifest.is_file():
        for line in manifest.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                rows[str(row["case_id"])] = row
    return rows


def load_case(adversary_dir: Path | str, case_id: str) -> AdversaryCase:
    """A prepared case with its derivation, from the manifest and derivations/."""
    adversary_dir = Path(adversary_dir)
    row = _load_manifest(adversary_dir).get(case_id)
    if row is None:
        raise ValueError(f"{adversary_dir}/cases.jsonl lists no case {case_id!r}")
    derivation_path = adversary_dir / "derivations" / f"{case_id}.md"
    derivation = derivation_path.read_text() if derivation_path.is_file() else ""
    return AdversaryCase.from_manifest_row(row, derivation)


def write_stage2_prompt(adversary_dir: Path | str, case_id: str) -> Path:
    """Write ``cases/<case_id>/stage2_prompt.md`` from a valid stage 1.

    Raises ``ValueError`` unless ``stage1.json`` satisfies
    :data:`STAGE1_SCHEMA`, cites no blocked source and is in the canonical
    form the runners publish (so the embedded text is the file, byte for
    byte, and the embedded sha256 is the file's). The stage-2 prompt embeds
    stage 1 and its sha256, so a re-judged stage 1 changes it. A
    verdict judged on another stage-2 prompt is deleted with its sidecar: one
    is kept only if the stored prompt is unchanged, or if its bound sidecar
    records the new prompt's sha256.
    """
    adversary_dir = Path(adversary_dir)
    case = load_case(adversary_dir, case_id)
    case_dir = adversary_dir / "cases" / case_id
    stage1, stage1_sha, errors = _read_output(case_dir / STAGE1_FILE, STAGE1_SCHEMA)
    if stage1 is None:
        raise ValueError(f"{case_id}: no valid stage 1 ({'; '.join(errors)})")
    if sha256_text(canonical_json(stage1)) != stage1_sha:
        raise ValueError(
            f"{case_id}: stage1.json is not in canonical form, so no runner "
            "published it; re-run stage 1"
        )
    prompt = render_stage2_prompt(case, stage1, stage1_sha)
    path = case_dir / STAGE2_PROMPT
    unchanged = path.is_file() and path.read_text() == prompt
    if not unchanged:
        meta = bound_sidecar(case_dir / VERDICT_FILE, case_dir / VERDICT_META)
        if not (meta and meta.get("prompt_sha256") == sha256_text(prompt)):
            _unlink(case_dir, (VERDICT_FILE, VERDICT_META))
    path.write_text(prompt)
    return path


# --- Collection ----------------------------------------------------------------

_VERDICT_COLUMNS = [
    "case_id",
    "country",
    "scenario_id",
    "variable",
    "verdict",
    "suggested_adjudication",
    "confidence",
    "reference_value",
    "consensus_value",
    "independent_answer",
    "stage1_law_supports",
    "engine_step_at_issue",
    "stage1_error",
    "summary",
    "citations",
    "judge_model",
]


def _differs(a: Any, b: Any) -> bool:
    """Whether two answers (numbers or null) differ beyond the tolerance."""
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(float(a) - float(b)) > VALUE_TOLERANCE


def verdict_problems(stage1: dict, verdict: dict, case_row: dict) -> list[str]:
    """Why a schema-valid verdict does not hang together with its case.

    The checks: the suggestion fits the verdict (:data:`VERDICT_SUGGESTIONS`);
    an engine step is named exactly when the reference is wrong or mismatched
    (and never when it holds); the verdict departs from stage 1's answer or
    finding only with a ``stage1_error``; its ``reference_value`` is the
    case's; its ``consensus_value`` is one of the case's consensus answers.
    """
    problems = []
    name = verdict["verdict"]
    suggested = verdict["suggested_adjudication"]
    stage1_error = verdict["stage1_error"].strip()
    step = verdict["engine_step_at_issue"].strip()
    if suggested not in VERDICT_SUGGESTIONS[name]:
        problems.append(f"{name} with suggested_adjudication {suggested}")
    if name == "reference_holds" and step:
        problems.append("reference_holds names an engine step at issue")
    if name in ("reference_wrong", "definition_mismatch") and not step:
        problems.append(f"{name} names no engine step at issue")
    if not stage1_error:
        supports = stage1["law_supports"]
        if supports == "consensus" and name == "reference_holds":
            problems.append(
                "stage 1 found the law supports the consensus; the verdict holds "
                "the reference without naming a stage-1 error"
            )
        if supports == "reference" and name == "reference_wrong":
            problems.append(
                "stage 1 found the law supports the reference; the verdict calls "
                "it wrong without naming a stage-1 error"
            )
        if _differs(stage1["independent_answer"], verdict["independent_answer"]):
            problems.append(
                f"the verdict's independent answer ({verdict['independent_answer']}) "
                f"departs from stage 1's ({stage1['independent_answer']}) without "
                "naming a stage-1 error"
            )
    reference = float(case_row["reference_value"])
    if _differs(verdict["reference_value"], reference):
        problems.append(
            f"the verdict's reference_value {verdict['reference_value']} is not the "
            f"case's reference {reference}"
        )
    consensus_value = verdict["consensus_value"]
    answers = [float(cluster["answer"]) for cluster in case_row.get("consensus", [])]
    if consensus_value is not None and answers:
        if all(_differs(consensus_value, answer) for answer in answers):
            problems.append(
                f"consensus_value {consensus_value} matches no consensus cluster "
                f"({', '.join(_number(a) for a in answers)})"
            )
    return problems


def _judge_model(meta: dict | None) -> str:
    if not meta:
        return "unknown"
    reported = meta.get("judge_model_reported") or []
    if isinstance(reported, str):
        reported = [reported]
    if reported:
        return "+".join(str(model) for model in reported)
    requested = meta.get("judge_model_requested")
    return str(requested) if requested else "unknown"


def collect_adversary(adversary_dir: Path | str) -> dict[str, pd.DataFrame]:
    """Fold the judges' outputs into tables; changes no file.

    Returns ``{"verdicts": ..., "missing": ..., "inconsistent": ...}``.
    ``verdicts`` has one row per case with a valid verdict built on a valid
    stage 1; ``citations`` is the verdict's citations as a JSON string and
    ``judge_model`` comes from the verdict's bound sidecar ("unknown"
    without one). ``missing`` lists cases with no such verdict and why: no
    verdict, an invalid one, no valid stage 1, a verdict with no bound
    sidecar, or a verdict whose sidecar or stage-2 prompt was built on another
    stage 1 (the sidecar must name the current stage 1's sha256, so a verdict
    is never taken as bound by default). ``inconsistent`` lists one
    row per problem :func:`verdict_problems` finds, and a stage 1 and verdict
    from different runners; those cases stay in ``verdicts`` too.
    """
    import pandas as pd

    adversary_dir = Path(adversary_dir)
    manifest = _load_manifest(adversary_dir)
    cases_root = adversary_dir / "cases"
    rows: list[dict] = []
    missing: list[dict] = []
    inconsistent: list[dict] = []
    for case_id, row in manifest.items():
        case_dir = cases_root / case_id
        key = {
            "case_id": case_id,
            "scenario_id": row["scenario_id"],
            "variable": row["variable"],
        }
        verdict, _, verdict_errors = _read_output(
            case_dir / VERDICT_FILE, VERDICT_SCHEMA
        )
        stage1, stage1_sha, stage1_errors = _read_output(
            case_dir / STAGE1_FILE, STAGE1_SCHEMA
        )
        if verdict_errors == ["absent"]:
            missing.append({**key, "reason": "no verdict"})
            continue
        if verdict is None:
            missing.append(
                {**key, "reason": f"invalid verdict: {'; '.join(verdict_errors)}"}
            )
            continue
        if stage1 is None:
            missing.append(
                {
                    **key,
                    "reason": "the verdict has no valid stage 1: "
                    + "; ".join(stage1_errors),
                }
            )
            continue
        meta = bound_sidecar(case_dir / VERDICT_FILE, case_dir / VERDICT_META)
        if not meta:
            missing.append({**key, "reason": "the verdict has no sidecar bound to it"})
            continue
        if meta.get("stage1_sha256") != stage1_sha:
            missing.append(
                {**key, "reason": "the verdict was judged on another stage 1"}
            )
            continue
        stage2_prompt = case_dir / STAGE2_PROMPT
        if stage2_prompt.is_file() and stage1_sha not in stage2_prompt.read_text():
            missing.append(
                {
                    **key,
                    "reason": "the stage-2 prompt was built on another stage 1",
                }
            )
            continue
        for problem in verdict_problems(stage1, verdict, row):
            inconsistent.append({**key, "problem": problem})
        stage1_meta = bound_sidecar(case_dir / STAGE1_FILE, case_dir / STAGE1_META)
        if (
            meta
            and stage1_meta
            and meta.get("judge_runner") != stage1_meta.get("judge_runner")
        ):
            inconsistent.append(
                {
                    **key,
                    "problem": "stage 1 and the verdict come from different runners "
                    f"({stage1_meta.get('judge_runner')}, {meta.get('judge_runner')})",
                }
            )
        rows.append(
            {
                "case_id": case_id,
                "country": row["country"],
                "scenario_id": row["scenario_id"],
                "variable": row["variable"],
                "verdict": verdict["verdict"],
                "suggested_adjudication": verdict["suggested_adjudication"],
                "confidence": verdict["confidence"],
                "reference_value": float(row["reference_value"]),
                "consensus_value": verdict["consensus_value"],
                "independent_answer": verdict["independent_answer"],
                "stage1_law_supports": stage1["law_supports"],
                "engine_step_at_issue": verdict["engine_step_at_issue"],
                "stage1_error": verdict["stage1_error"],
                "summary": verdict["summary"],
                "citations": json.dumps(verdict["citations"], sort_keys=True),
                "judge_model": _judge_model(meta),
            }
        )
    return {
        "verdicts": pd.DataFrame(rows, columns=_VERDICT_COLUMNS),
        "missing": pd.DataFrame(
            missing, columns=["case_id", "scenario_id", "variable", "reason"]
        ),
        "inconsistent": pd.DataFrame(
            inconsistent, columns=["case_id", "scenario_id", "variable", "problem"]
        ),
    }


_MERGED_FIELDS = (
    "verdict",
    "suggested_adjudication",
    "confidence",
    "independent_answer",
    "consensus_value",
    "stage1_law_supports",
    "engine_step_at_issue",
    "stage1_error",
    "summary",
    "judge_model",
)
_CASE_FIELDS = ("case_id", "country", "scenario_id", "variable", "reference_value")


def merge_judges(verdicts_by_judge: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per case across judges, keyed by each judge's label.

    Each judge contributes ``<label>_verdict``, ``<label>_suggested_adjudication``
    and the rest of its verdict fields. ``verdicts`` is a JSON object of the
    judges' verdicts (judges without a verdict for the case are left out),
    ``judges`` counts them, and ``agree`` is true when every judge returned a
    verdict and all are the same.
    """
    import pandas as pd

    labels = list(verdicts_by_judge)
    for label in labels:
        if not label or not isinstance(label, str):
            raise ValueError(f"judge labels must be non-empty strings: {label!r}")
    cases: dict[str, dict] = {}
    for label, frame in verdicts_by_judge.items():
        for record in frame.to_dict("records"):
            case = cases.setdefault(
                str(record["case_id"]), {f: record[f] for f in _CASE_FIELDS}
            )
            if label in case.get("_by_judge", {}):
                raise ValueError(f"{label} has two verdicts for {record['case_id']}")
            case.setdefault("_by_judge", {})[label] = record
    columns = [
        *_CASE_FIELDS,
        *(f"{label}_{name}" for label in labels for name in _MERGED_FIELDS),
        "verdicts",
        "judges",
        "agree",
    ]
    rows = []
    for case_id in sorted(cases):
        case = cases[case_id]
        by_judge = case.pop("_by_judge")
        row = dict(case)
        for label in labels:
            record = by_judge.get(label)
            for name in _MERGED_FIELDS:
                row[f"{label}_{name}"] = None if record is None else record[name]
        verdicts = {
            label: by_judge[label]["verdict"] for label in labels if label in by_judge
        }
        row["verdicts"] = json.dumps(verdicts, sort_keys=True)
        row["judges"] = len(verdicts)
        row["agree"] = len(verdicts) == len(labels) and len(set(verdicts.values())) == 1
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


QUEUE_COLUMNS = [
    "country",
    "scenario_id",
    "variable",
    "reference_suspect",
    "reference_bug_hypothesis",
    "reference_suspect_source",
    "adversary_verdicts",
    "suggested_adjudication",
]
SUSPECT_SOURCE = "reference_adversary"


def _hypothesis(judge: str, verdict: str, summary: Any, step: Any) -> str:
    text = f"Reference adversary ({judge}): {verdict}. {_clean(summary)}".rstrip()
    step = _clean(step)
    if step:
        text += f" Engine step at issue: {step}"
    return text


def adjudication_queue(
    verdicts: pd.DataFrame, inconsistent: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Cases for developer adjudication, in the case-notes schema.

    Takes a ``collect_adversary`` verdict table (a case is queued when its
    verdict is not ``reference_holds``) or a ``merge_judges`` table (queued
    when any judge's verdict is not). A case with a row in ``inconsistent``
    (``collect_adversary``'s table, optionally with a ``judge`` column) is
    queued whatever its verdicts, with the problems in its hypothesis: a
    ``reference_holds`` that, say, silently drops stage 1's finding for the
    consensus is exactly what the two stages exist to catch. Each queued case carries
    ``reference_suspect`` true, a ``reference_bug_hypothesis`` naming each
    judge's verdict, summary and engine step, ``reference_suspect_source``
    "reference_adversary", the judges' verdicts as JSON and the suggested
    adjudication (one value when the judges agree on it, else per judge).
    """
    import pandas as pd

    rows = []
    merged = "verdict" not in verdicts.columns
    if merged and "verdicts" not in verdicts.columns:
        raise ValueError("expected a collect_adversary or merge_judges table")
    problems: dict[str, list[str]] = {}
    if inconsistent is not None:
        for row in inconsistent.to_dict("records"):
            judge = _clean(row.get("judge"))
            problem = _clean(row.get("problem"))
            problems.setdefault(str(row["case_id"]), []).append(
                f"{judge}: {problem}" if judge else problem
            )
    for record in verdicts.to_dict("records"):
        flagged = problems.get(str(record["case_id"]), [])
        if merged:
            by_judge = json.loads(record["verdicts"])
            if not flagged and all(v == "reference_holds" for v in by_judge.values()):
                continue
            hypotheses = [
                _hypothesis(
                    label,
                    verdict,
                    record.get(f"{label}_summary"),
                    record.get(f"{label}_engine_step_at_issue"),
                )
                for label, verdict in sorted(by_judge.items())
            ]
            suggestions = {
                label: _clean(record.get(f"{label}_suggested_adjudication"))
                for label in sorted(by_judge)
            }
            distinct = set(suggestions.values())
            suggested = (
                distinct.pop()
                if len(distinct) == 1
                else "; ".join(f"{label}: {s}" for label, s in suggestions.items())
            )
            adversary_verdicts = by_judge
        else:
            if not flagged and record["verdict"] == "reference_holds":
                continue
            judge = _clean(record.get("judge_model")) or "unknown"
            hypotheses = [
                _hypothesis(
                    judge,
                    record["verdict"],
                    record.get("summary"),
                    record.get("engine_step_at_issue"),
                )
            ]
            suggested = _clean(record.get("suggested_adjudication"))
            adversary_verdicts = {judge: record["verdict"]}
        rows.append(
            {
                "country": record["country"],
                "scenario_id": record["scenario_id"],
                "variable": record["variable"],
                "reference_suspect": True,
                "reference_bug_hypothesis": " | ".join(
                    hypotheses
                    + [f"Inconsistent verdict: {problem}" for problem in flagged]
                ),
                "reference_suspect_source": SUSPECT_SOURCE,
                "adversary_verdicts": json.dumps(adversary_verdicts, sort_keys=True),
                "suggested_adjudication": suggested,
            }
        )
    return pd.DataFrame(rows, columns=QUEUE_COLUMNS)


_CASE_KEY = ("country", "scenario_id", "variable")


def apply_adversary_flags(
    case_notes: pd.DataFrame, queue: pd.DataFrame
) -> pd.DataFrame:
    """Flag the queued cases reference-suspect in a copy of the case notes.

    Each queued case gets ``reference_suspect`` true and the queue's
    hypothesis (appended after any hypothesis the case already carries), and
    ``reference_suspect_source`` (added when absent, "" for other cases) gains
    "reference_adversary". No other column changes, no flag is cleared, and
    applying the same queue twice changes nothing more. A queued case missing
    from the case notes raises ``ValueError``: the queue must not name a case
    the notes cannot carry.
    """
    import pandas as pd

    if case_notes.columns.duplicated().any():
        raise ValueError("the case notes repeat a column name")
    notes = case_notes.copy()
    if "reference_suspect" not in notes.columns:
        notes["reference_suspect"] = False
    for column in ("reference_bug_hypothesis", "reference_suspect_source"):
        if column not in notes.columns:
            notes[column] = ""
        notes[column] = notes[column].astype(object)
    if notes["reference_suspect"].dtype != bool:
        notes["reference_suspect"] = notes["reference_suspect"].astype(object)
    flag = notes.columns.get_loc("reference_suspect")
    said = notes.columns.get_loc("reference_bug_hypothesis")
    origin = notes.columns.get_loc("reference_suspect_source")
    for record in queue.to_dict("records"):
        mask = pd.Series(True, index=notes.index)
        for column in _CASE_KEY:
            mask &= notes[column].astype(str) == str(record[column])
        if not mask.any():
            raise ValueError(
                "the adversary queue names a case the case notes lack: "
                f"{[record[column] for column in _CASE_KEY]}"
            )
        hypothesis = _clean(record.get("reference_bug_hypothesis"))
        for position in [i for i, hit in enumerate(mask.to_numpy()) if hit]:
            notes.iat[position, flag] = True
            existing = _clean(notes.iat[position, said])
            if hypothesis and hypothesis not in existing:
                notes.iat[position, said] = (
                    f"{existing} | {hypothesis}" if existing else hypothesis
                )
            source = _clean(notes.iat[position, origin])
            if SUSPECT_SOURCE not in source.split(";"):
                notes.iat[position, origin] = (
                    f"{source};{SUSPECT_SOURCE}" if source else SUSPECT_SOURCE
                )
    return notes


# --- Judge activity audits -----------------------------------------------------


def _markers_in(text: str) -> list[str]:
    lowered = str(text or "").lower()
    return [marker for marker in DERIVATION_MARKERS if marker in lowered]


def codex_events_audit(events_text: str) -> tuple[list[str], dict]:
    """Audit a ``codex exec --json`` event log for contamination.

    Inspects only tool activity, never the judge's messages or reasoning
    (which may quote the output definition's own mention of PolicyEngine):
    each shell command and its output, and each web search's query and action
    (an opened URL or an in-page search). A :data:`DERIVATION_MARKERS` string
    in any of them, an opened URL on a blocked domain, any tool item of
    another type (an MCP call, a file change) and any line that is not a JSON
    event but carries a marker are problems. Returns the problems and the
    activity (searches, opened URLs, commands, thread id) for the sidecar.
    """
    problems: list[str] = []
    activity: dict[str, Any] = {
        "searches": [],
        "fetches": [],
        "commands": [],
        "thread_id": None,
    }
    seen_items: set[str] = set()
    for number, line in enumerate(events_text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if not isinstance(event, dict):
            for marker in _markers_in(line):
                problems.append(f"line {number}: non-event output names {marker!r}")
            continue
        if event.get("type") == "thread.started":
            activity["thread_id"] = event.get("thread_id")
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        completed = event.get("type") == "item.completed"
        if kind in CODEX_QUIET_ITEMS:
            continue
        if kind not in CODEX_AUDITED_ITEMS:
            problems.append(f"line {number}: the judge used a {kind!r} tool")
            continue
        if kind == "command_execution":
            command = str(item.get("command") or "")
            output = str(item.get("aggregated_output") or "")
            for marker in _markers_in(command):
                problems.append(f"line {number}: a command names {marker!r}: {command}")
            for marker in _markers_in(output):
                problems.append(f"line {number}: a command's output names {marker!r}")
            if completed and item.get("id") not in seen_items:
                activity["commands"].append(command)
        else:
            # codex-cli 0.159.0 shapes: a search's action carries "query" or a
            # "queries" list; open_page carries "url" (and the item's query
            # repeats it); find_in_page carries "pattern" and maybe "url".
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            queries = action.get("queries")
            searched = [
                str(text)
                for text in [
                    action.get("query"),
                    *(queries if isinstance(queries, list) else []),
                ]
                if text
            ]
            url = str(action.get("url") or "")
            for text in [str(item.get("query") or ""), *searched]:
                for marker in _markers_in(text):
                    problems.append(f"line {number}: a web search names {marker!r}")
            for marker in _markers_in(str(action.get("pattern") or "")):
                problems.append(f"line {number}: an in-page search names {marker!r}")
            if url and (blocked_url(url) or _markers_in(url)):
                problems.append(f"line {number}: the judge opened a blocked URL: {url}")
            if completed and item.get("id") not in seen_items:
                if url:
                    activity["fetches"].append(url)
                elif searched or item.get("query"):
                    activity["searches"] += searched or [str(item["query"])]
        if completed:
            seen_items.add(str(item.get("id")))
    return sorted(set(problems)), activity


def _tool_name(part: dict) -> str:
    name = str(part.get("name") or part.get("type") or "")
    return {"web_search": "WebSearch", "web_fetch": "WebFetch"}.get(name, name)


def claude_transcript_audit(
    transcript_text: str, prompt_text: str
) -> tuple[list[str], dict, list[dict]]:
    """Audit a Claude Code session transcript of one adversary call.

    Problems: a tool call other than WebSearch, WebFetch or StructuredOutput;
    a fetch of a blocked URL that returned content (a fetch the runner's deny
    rule refused, whose result is an error, returned nothing and is recorded
    as a denied attempt instead); a search naming the engine or the benchmark;
    a search whose result reached the judge listing a URL on a blocked domain
    or naming the engine or the benchmark, or whose text names them (WebSearch
    has no deny rule, so its results reach the judge; the prompt asks for
    blocked_domains on every search, and this check enforces the outcome); a
    user text message other than the judged prompt (Claude Code's own
    StructuredOutput nudge aside). Returns the problems, the web activity for
    the sidecar, and the inputs of the StructuredOutput calls the schema
    accepted (calls whose result was not an error).
    """
    problems: list[str] = []
    activity: dict[str, list[str]] = {
        "searches": [],
        "fetches": [],
        "denied_fetches": [],
    }
    blocked_fetches: list[tuple[str, str]] = []
    searches: list[tuple[str, str]] = []
    results: dict[str, str] = {}
    texts: list[str] = []
    calls: list[dict] = []
    refused: set[str] = set()
    for number, line in enumerate(transcript_text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"transcript line {number} is not JSON")
            continue
        if not isinstance(event, dict):
            problems.append(f"transcript line {number} is not an event")
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("type") == "user":
            if isinstance(content, str):
                if not (
                    event.get("isMeta") is True
                    and content.startswith("[structured-output-enforce]")
                ):
                    texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        texts.append(str(part.get("text", "")))
                    if part.get("type") == "tool_result":
                        call_id = str(part.get("tool_use_id"))
                        results[call_id] = results.get(call_id, "") + _result_text(
                            part.get("content")
                        )
                        if part.get("is_error"):
                            refused.add(call_id)
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or not str(part.get("type", "")).endswith(
                "tool_use"
            ):
                continue
            name = _tool_name(part)
            payload = part.get("input") if isinstance(part.get("input"), dict) else {}
            if name == "StructuredOutput":
                calls.append(part)
            elif name == "WebFetch":
                url = str(payload.get("url") or "")
                if blocked_url(url):
                    blocked_fetches.append((str(part.get("id")), url))
                else:
                    activity["fetches"].append(url)
            elif name == "WebSearch":
                query = str(payload.get("query") or "")
                activity["searches"].append(query)
                searches.append((str(part.get("id")), query))
                if any(n in query.lower() for n in BLOCKED_NAMES):
                    problems.append(f"the judge searched for the engine: {query}")
            else:
                problems.append(f"the judge called a tool it was not given: {name}")
    for call_id, query in searches:
        exposed = blocked_search_result(results.get(call_id, ""))
        if exposed:
            problems.append(
                f"a search returned a blocked source: {query} -> {', '.join(exposed)}"
            )
    for call_id, url in blocked_fetches:
        if call_id in refused:
            activity["denied_fetches"].append(url)
        else:
            problems.append(f"the judge fetched a blocked URL: {url}")
    if [text.strip() for text in texts] != [prompt_text.strip()]:
        problems.append(
            f"{len(texts)} user text messages, not exactly the judged prompt"
        )
    accepted = [
        part.get("input") for part in calls if str(part.get("id")) not in refused
    ]
    return problems, activity, accepted


# --- Publishing judge outputs --------------------------------------------------


class FinalizeError(Exception):
    """A judge call produced nothing publishable; ``code`` is the exit status."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _parse_json_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    index = text.find("{")
    while index != -1:
        try:
            document, _ = decoder.raw_decode(text[index:])
        except ValueError:
            document = None
        if isinstance(document, dict):
            return document
        index = text.find("{", index + 1)
    return None


def _claude_output(args: argparse.Namespace, prompt_text: str) -> tuple[Any, dict]:
    """The judge's answer from a Claude envelope, after the transcript audit."""
    try:
        envelope = json.loads(Path(args.raw).read_text())
    except (OSError, ValueError) as exc:
        raise FinalizeError(f"no CLI envelope: {exc}") from exc
    if not isinstance(envelope, dict):
        raise FinalizeError("the CLI envelope is not an object")
    if envelope.get("is_error"):
        status = envelope.get("api_error_status")
        what = (
            "the CLI's login cannot judge now"
            if status in (401, 403, 429)
            else "the CLI reported an error"
        )
        raise FinalizeError(
            f"{what}: status {status}: {envelope.get('result')}",
            7 if status in (401, 403, 429) else 1,
        )
    document = envelope.get("structured_output")
    if document is None and isinstance(envelope.get("result"), str):
        document = _parse_json_text(envelope["result"])
    if not isinstance(document, dict):
        raise FinalizeError("the judge returned no JSON object")
    session = envelope.get("session_id")
    found = (
        glob.glob(f"{glob.escape(args.config_dir)}/projects/*/{session}.jsonl")
        if session and args.config_dir
        else []
    )
    if len(found) != 1:
        raise FinalizeError(
            f"no single transcript for session {session} in {args.config_dir}", 3
        )
    if args.transcript_out:
        shutil.copyfile(found[0], args.transcript_out)
    problems, activity, accepted = claude_transcript_audit(
        Path(found[0]).read_text(), prompt_text
    )
    if problems:
        raise FinalizeError(f"contaminated: {problems}", 2)
    if len(accepted) != 1 or canonical_json(accepted[0]) != canonical_json(document):
        raise FinalizeError(
            "the output is not the judge's one accepted StructuredOutput answer", 3
        )
    meta = {
        "judge_model_reported": sorted((envelope.get("modelUsage") or {}).keys()),
        "session_id": session,
        "web_activity": activity,
        "cost_usd": envelope.get("total_cost_usd"),
        "duration_ms": envelope.get("duration_ms"),
        "tool_policy": {
            "allowed_tools": list(CLAUDE_ALLOWED_TOOLS),
            "blocked_domains": list(BLOCKED_DOMAINS),
            "enforcement": "--tools and --disallowedTools WebFetch(domain:...) "
            "rules, then a transcript audit",
        },
    }
    if args.auth:
        meta["judge_auth"] = json.loads(args.auth)
    if args.account:
        meta["judge_account_declared"] = args.account
    return document, meta


def _codex_output(args: argparse.Namespace) -> tuple[Any, dict]:
    """The judge's answer from Codex's -o file, after the event-log audit."""
    try:
        events = Path(args.events).read_text(errors="replace")
    except OSError as exc:
        raise FinalizeError(f"no codex event log: {exc}", 3) from exc
    problems, activity = codex_events_audit(events)
    if args.log:
        # In --json mode the prompt is not echoed: the stderr of the codex-cli
        # --json runs in ~/.subfleet/jobs examined on 2026-10-05 held only
        # status lines ("Reading prompt from stdin...", an occasional ERROR),
        # so a marker there is not the prompt's own text.
        try:
            stderr = Path(args.log).read_text(errors="replace")
        except OSError:
            stderr = ""
        for number, line in enumerate(stderr.splitlines(), 1):
            for marker in _markers_in(line):
                problems.append(f"stderr line {number} names {marker!r}")
    if problems:
        raise FinalizeError(f"contaminated: {problems}", 2)
    try:
        document = _parse_json_text(Path(args.raw).read_text())
    except OSError as exc:
        raise FinalizeError(f"no codex output: {exc}") from exc
    meta = {
        "judge_model_reported": [],
        "session_id": activity.pop("thread_id"),
        "web_activity": activity,
        "tool_policy": {
            "allowed_tools": ["web_search (--search)", "shell (read-only sandbox)"],
            "blocked_domains": list(BLOCKED_DOMAINS),
            "enforcement": "event-log audit of every command, search and opened URL",
        },
    }
    return document, meta


def finalize(args: argparse.Namespace) -> int:
    """Validate a judge call's output and write it and its sidecar atomically.

    The runner calls this after each CLI call. It checks that the judged copy
    of the prompt still has the hash taken before the call and that the
    case's prompt file still has it; audits the call (the Claude transcript,
    or the Codex event log); validates the output against the stage's schema
    and the blocked-source rule; for stage 2, checks that the judged prompt
    embeds the current stage 1's sha256. It then writes the output in
    canonical form to ``--out`` and the sidecar to ``--meta``, which the
    runner moves into place.
    """
    stage = int(args.stage)
    prompt_bytes = Path(args.prompt_file).read_bytes()
    if hashlib.sha256(prompt_bytes).hexdigest() != args.prompt_sha256:
        raise FinalizeError("the judged copy of the prompt changed", 3)
    if args.case_prompt and _sha256_file(Path(args.case_prompt)) != args.prompt_sha256:
        raise FinalizeError("the case's prompt changed while the judge ran", 3)
    prompt_text = prompt_bytes.decode("utf-8")
    if args.runner == "claude":
        document, meta = _claude_output(args, prompt_text)
    else:
        document, meta = _codex_output(args)
    if not isinstance(document, dict):
        raise FinalizeError("the judge returned no JSON object")
    schema = json.loads(Path(args.schema).read_text())
    errors = output_errors(schema, document)
    if errors:
        raise FinalizeError(f"invalid output: {errors}")
    stage1_sha = None
    stage1_runner = None
    if stage == 2:
        if not args.stage1:
            raise FinalizeError("stage 2 needs --stage1", 3)
        stage1_path = Path(args.stage1)
        if not stage1_path.is_file():
            raise FinalizeError(f"no stage 1 at {stage1_path}", 3)
        stage1_sha = _sha256_file(stage1_path)
        if stage1_sha not in prompt_text:
            raise FinalizeError(
                "the judged prompt does not embed the current stage 1", 3
            )
        stage1_meta = bound_sidecar(stage1_path, stage1_path.with_name(STAGE1_META))
        stage1_runner = (stage1_meta or {}).get("judge_runner")
    text = canonical_json(document)
    Path(args.out).write_text(text)
    sidecar = {
        "judge_runner": RUNNERS[args.runner],
        "stage": stage,
        "output_file": STAGE1_FILE if stage == 1 else VERDICT_FILE,
        "output_sha256": sha256_text(text),
        "prompt_file": STAGE1_PROMPT if stage == 1 else STAGE2_PROMPT,
        "prompt_sha256": args.prompt_sha256,
        "judge_model_requested": args.model_requested or "default",
        "judge_cli_version": args.cli_version,
        "judge_effort": args.effort,
        "judged_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "blinding": BLINDING[args.runner],
        **meta,
    }
    if stage == 2:
        sidecar["stage1_sha256"] = stage1_sha
        sidecar["stage1_judge_runner"] = stage1_runner
    Path(args.meta).write_text(json.dumps(sidecar, indent=2, sort_keys=True))
    return 0


def check_login(
    status_text: str,
    desktop_text: str,
    *,
    token: bool,
    declared: str,
    config_dir: str,
    desktop_opt_in: bool,
) -> dict:
    """The Claude login a runner may judge with, or ``ValueError`` saying why not.

    The same rule as ``scripts/run_audit_claude.sh``: a first-party
    subscription login (a lane token or a claude.ai login) that is not the
    desktop login's account, unless the desktop login is explicitly opted in,
    in which case it must be exactly the desktop's own claude.ai login.
    """

    def parse(text: str) -> dict:
        try:
            value = json.loads(text)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    status, desktop = parse(status_text), parse(desktop_text)
    method, email = status.get("authMethod"), status.get("email")
    reported = status.get("configDirectory")
    if status.get("loggedIn") is not True:
        raise ValueError(f"claude auth status reports no login in {config_dir}")
    if status.get("apiProvider") != "firstParty":
        raise ValueError(
            f"the login is through {status.get('apiProvider')!r}, not a "
            "first-party subscription"
        )
    if method not in ("oauth_token", "claude.ai"):
        raise ValueError(f"the login method {method!r} is not a subscription login")
    same_account = bool(
        email and desktop.get("loggedIn") is True and email == desktop.get("email")
    )
    if desktop_opt_in:
        if method != "claude.ai":
            raise ValueError(
                f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the CLI logs in by {method!r}"
            )
        if not same_account:
            raise ValueError(
                f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the login ({email}) is not the "
                "desktop login's account"
            )
        if not (
            isinstance(reported, str)
            and os.path.isdir(reported)
            and os.path.samefile(reported, config_dir)
        ):
            raise ValueError(
                f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the CLI reports config "
                f"directory {reported!r}, not {config_dir}"
            )
    else:
        if token and method != "oauth_token":
            raise ValueError(f"a lane token is set but the CLI logs in by {method!r}")
        if method == "oauth_token" and not declared:
            raise ValueError(
                "a token login reports no account; set AUDIT_ACCOUNT to the lane's"
            )
        if (
            method == "oauth_token"
            and desktop.get("loggedIn") is True
            and declared.strip().lower()
            == str(desktop.get("email") or "").strip().lower()
        ):
            raise ValueError(
                f"AUDIT_ACCOUNT ({declared}) is the desktop login's account"
            )
        if same_account:
            raise ValueError(f"the login is the desktop login's account ({email})")
    return {"method": method, "account": email, "org": status.get("orgId")}


# --- Command line --------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point the runners call: ``python -m policybench.reference_adversary``.

    Commands: ``render-stage2 --adversary-dir D --case-id X`` writes a case's
    stage-2 prompt (exit 1 without a valid stage 1); ``validate --schema S
    --file F`` exits 0 when F satisfies S and cites no blocked source, else 1;
    ``finalize`` publishes one judge call's output and sidecar (see
    :func:`finalize`); ``check-login`` vets the Claude runner's login.
    """
    parser = argparse.ArgumentParser(
        prog="python -m policybench.reference_adversary",
        description="Deterministic steps of the reference adversary's runners.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render-stage2")
    render.add_argument("--adversary-dir", required=True)
    render.add_argument("--case-id", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--schema", required=True)
    validate.add_argument("--file", required=True)
    fin = commands.add_parser("finalize")
    fin.add_argument("--runner", choices=sorted(RUNNERS), required=True)
    fin.add_argument("--stage", choices=["1", "2"], required=True)
    fin.add_argument("--raw", required=True, help="Claude envelope or Codex -o file")
    fin.add_argument("--events", default=None, help="Codex --json event log")
    fin.add_argument("--log", default="", help="Codex stderr, audited too")
    fin.add_argument("--schema", required=True)
    fin.add_argument("--out", required=True)
    fin.add_argument("--meta", required=True)
    fin.add_argument("--prompt-file", required=True, help="the judged prompt copy")
    fin.add_argument("--prompt-sha256", required=True)
    fin.add_argument("--case-prompt", default=None)
    fin.add_argument("--stage1", default=None)
    fin.add_argument("--model-requested", default="")
    fin.add_argument("--cli-version", default="")
    fin.add_argument("--effort", default="")
    fin.add_argument("--config-dir", default="")
    fin.add_argument("--transcript-out", default="")
    fin.add_argument("--auth", default="")
    fin.add_argument("--account", default="")
    login = commands.add_parser("check-login")
    login.add_argument("--status", required=True)
    login.add_argument("--desktop-status", default="")
    login.add_argument("--token-set", choices=["0", "1"], default="0")
    login.add_argument("--declared", default="")
    login.add_argument("--config-dir", required=True)
    login.add_argument("--desktop-opt-in", choices=["0", "1"], default="0")
    args = parser.parse_args(argv)

    if args.command == "render-stage2":
        try:
            path = write_stage2_prompt(Path(args.adversary_dir), args.case_id)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(path)
        return 0
    if args.command == "validate":
        try:
            schema = json.loads(Path(args.schema).read_text())
            document = json.loads(Path(args.file).read_text())
        except (OSError, ValueError) as exc:
            print(f"unreadable: {exc}", file=sys.stderr)
            return 1
        errors = output_errors(schema, document)
        for error in errors:
            print(error, file=sys.stderr)
        return 1 if errors else 0
    if args.command == "finalize":
        if args.runner == "codex" and not args.events:
            print("the codex runner needs --events", file=sys.stderr)
            return 1
        try:
            return finalize(args)
        except FinalizeError as exc:
            print(str(exc), file=sys.stderr)
            return exc.code
    try:
        login_info = check_login(
            args.status,
            args.desktop_status,
            token=args.token_set == "1",
            declared=args.declared,
            config_dir=args.config_dir,
            desktop_opt_in=args.desktop_opt_in == "1",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(login_info, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
